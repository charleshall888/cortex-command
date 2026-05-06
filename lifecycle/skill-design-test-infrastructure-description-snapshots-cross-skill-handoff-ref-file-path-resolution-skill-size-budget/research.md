# Research: Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget)

> Backlog: #181 · Parent epic: #172 · Blocked-by: [178] · Tier: complex · Criticality: high
> Clarified intent: Add four CI-time test classes catching named regressions in cortex's skill-design surface — (1) trigger-phrase drift in SKILL.md descriptions, (2) silent renames of cross-skill handoff fields, (3) stale `<file>:<line>` citations, (4) unbudgeted SKILL.md growth. Test #1 corpus sourced from post-#178 SKILL.md descriptions. Test #2 is **static** schema/field validation (no live skill execution).

## Codebase Analysis

### Closest existing precedents

- **`bin/cortex-check-parity` + `tests/test_check_parity.py`** — the canonical lint-tool + pytest-driver template (1462 lines). Uses `Violation` dataclass with `path:line:col: CODE message` format, JSON output, `--self-test`, exit codes (0/1/2), `valid-/invalid-/exclude-` fixture-prefix protocol, and `bin/.parity-exceptions.md` allowlist (5-column markdown table, ≥30-char rationale, lifecycle id, dated). This is the project.md Architectural Constraints clause "SKILL.md-to-bin parity enforcement" in code form.
- **`tests/test_lifecycle_references_resolve.py`** (208 lines) — closest analog for test #3. Walks `git ls-files '*.md'` with five regex forms, asserts each citation resolves, gates coverage (`≥50 resolved, ≥1 per form`) to defeat regex-bug false-passes, pairs with `tests/fixtures/lifecycle_references/broken-citation.md` to prove the resolver detects breakage. **Scope is `lifecycle/` and `research/`, NOT `skills/`.**
- **`tests/test_skill_callgraph.py`** (108 lines) — uses `INVOCATION_RE` regex + `<!-- callgraph: ignore -->` suppression marker; imports its linter via `importlib.util.spec_from_file_location`. Validates the call exists in markdown but does not exercise it (per ticket body framing).
- **`tests/test_dual_source_reference_parity.py`** — glob-discovers `skills/*/SKILL.md` pairs and asserts byte-parity between canonical and `plugins/cortex-core/skills/` mirror. Implies test #3/#4 should target canonical only (mirror is provably identical post-pre-commit).
- **`tests/test_skill_contracts.py`** — fixture-prefix dispatch (`valid-/invalid-`) calling `scripts/validate-skill.py`.

### Files that will change

- `tests/test_skill_descriptions.py` (NEW) — trigger-phrase corpus assertion
- `tests/test_skill_handoff.py` (NEW) **OR extend** `tests/test_skill_callgraph.py` — static handoff schema check
- `tests/test_skill_reference_paths.py` (NEW) — citation resolver — **scope contested; see Adversarial §1 and Open Questions**
- `tests/test_skill_size_budget.py` (NEW) — SKILL.md line-count cap
- `tests/fixtures/skill_trigger_phrases.yaml` (NEW, declarative corpus — Fork E2)
- `tests/fixtures/skill_handoff_schema.yaml` (NEW, declarative handoff fields — Fork F1)
- `tests/fixtures/skill_design/{valid,invalid,exclude}-*/` (scenario tree)
- `justfile` — new `test-skill-design` recipe + wire into `test-skill-contracts` aggregator (current line ~350) and `test-skills` aggregator (~456)
- `tests/conftest.py` — possible shared `loaded_skills` / `skill_paths` fixture

### Convention anchors (stdlib-only, error aggregation, suppression markers)

- All cortex linters are **stdlib-only**. PyYAML is already a transitive dep; no new runtime deps needed.
- Errors **aggregated and emitted as a single multi-line `AssertionError`** (per `test_lifecycle_references_resolve.py`); never fail-fast on first finding.
- Suppression marker syntax: `<!-- callgraph: ignore -->` (existing); test #3 would adopt `<!-- citation: ignore -->` for false-positive escapes.
- Test the **canonical tree only** (`skills/`); rely on dual-source byte-parity gate for `plugins/cortex-core/skills/` mirror. Non-cortex-core plugins (`cortex-overnight`, `cortex-ui-extras`, `cortex-pr-review`, `android-dev-extras`, `cortex-dev-extras`) have hand-maintained SKILL.md files outside the canonical→mirror flow — explicit scope decision needed (see Open Questions).

### Empirical surveys

**Current canonical SKILL.md sizes** (lines):

| Skill | Lines | Skill | Lines |
|---|---|---|---|
| `diagnose` | **489** | `dev` | 262 |
| `overnight` | 403 | `research` | 254 |
| `lifecycle` | 380 | `refine` | 233 |
| `critical-review` | 365 | `morning-review` | 143 |
| `requirements` | 116 | `backlog` | 107 |
| `pr` | 92 | `discovery` | 71 |
| `commit` | 56 | | |

**`diagnose` at 489 has 11-line headroom under the proposed 500 cap** — the ticket body's claim that "`lifecycle` (380) and `critical-review` (365) are close to the cap" is factually outdated.

**Citation corpus survey across `skills/**/*.md`** (the test #3 surface):

- Total `<file>:<line>(-line)?` matches: **8**
- **Real load-bearing citations: 2** — both are sibling-file pointers in `skills/discovery/references/decompose.md` to `skills/discovery/references/research.md:148-154` and `orchestrator-review.md:22-30`.
- **Fake worked-example citations: 6** — `client.py:142`, `auth.py:88`, `cache.py:55`, `migrate.py:212` in `skills/critical-review/SKILL.md` (illustrative bug scenarios pointing at imaginary files); `[src/foo.py:42]`, `[src/bar.py:18]`, `[src/baz.py:88]` in `skills/discovery/references/research.md` (pattern-matching examples).
- **The audit's framing — `plan.md:107` references `plugins/cortex-core/skills/critical-review/SKILL.md:176-182` — describes citations that live in `lifecycle/{slug}/plan.md`, NOT in `skills/`.** Citations in lifecycle artifacts already have a near-existing test surface (`test_lifecycle_references_resolve.py`).

**Cross-skill handoff fields enumerated** (from `skills/backlog/references/schema.md` plus the lifecycle, refine, and discovery SKILL.md files):

- Backlog frontmatter: `discovery_source`, `research`, `spec`, `status`, `complexity`, `criticality`, `areas`, `parent`, `blocks`, `blocked-by`, `lifecycle_slug`, `lifecycle_phase`, `session_id`, `tags`, `priority`, `type`
- Lifecycle artifact filenames: `research.md`, `spec.md`, `plan.md`, `index.md`, `events.log`, `review.md`, `orchestrator-note.md`, `preflight.md`, `learnings/progress.txt`, `deferred/{feature}-q{NNN}.md`
- events.log event types: `lifecycle_start`, `phase_transition`, `complexity_override`, `criticality_override`, `confidence_check`, `requirements_updated`, `feature_complete`, `clarify_critic`, `discovery_reference`
- Lifecycle index.md frontmatter: `feature`, `parent_backlog_uuid`, `parent_backlog_id`, `artifacts`, `tags`, `created`, `updated`
- Spec.md / plan.md sections: `## Non-Requirements`, `## Open Decisions`, `## Open Questions`, per-task `Files`, `Depends on`, `Complexity` (these are read by `pipeline/parser.py:332-374`)

## Web Research

### Anthropic skill-design conventions (authoritative)

- **"Keep SKILL.md body under 500 lines for optimal performance"** — appears verbatim twice in Anthropic's Skill authoring best practices. Authoring checklist includes literal item: `[ ] SKILL.md body is under 500 lines`.
- Description-as-trigger is explicit: "Each Skill has exactly one description field. The description is critical for skill selection: Claude uses it to choose the right Skill from potentially 100+ available Skills." Description hard limits: max 1024 characters, third person, non-empty.
- "File references are one level deep" — structural rule that test #3 could co-enforce.
- Anthropic publishes **no official skill-design test template**: "There is not currently a built-in way to run these evaluations. Users can create their own evaluation system." Cortex's tests would be original work.
- Practitioner data: activation rates measured at 20% → 50% → 90% as descriptions move from vague → specific → example-laden (Scott Spence "650-trial" study). Validates that trigger phrases are load-bearing and worth gating.

### Snapshot vs. assertion-style for trigger-phrase corpus

- **Substring-presence (`assert phrase in description`) preferred over snapshot tooling** for cortex's case. The contract is "description contains curated phrase set," not "description equals snapshot."
- Snapshot fails on legitimate prose tweaks (high false-positive rate); substring fails only when a curated phrase is dropped (aligned signal).
- Snapshot-update workflows (`syrupy --snapshot-update`) require interactive dev step that overnight-runner can't perform.

### Citation drift detection

- **No standardized line-anchored citation format exists**. `<file>:<line>` is cortex-specific (compiler-error-output style). GitHub `#L10-L20` permalinks are explicitly documented as fragile.
- `md-link-checker`, `markdown-checker`, `linkcheckmd`, `mkdocs-linkcheck` validate link existence but **none validate line counts**. Cortex would extend the pattern, not adopt one.
- Closest external prior art: **DocSync** (HN Show post #47021705) — tree-sitter symbol-based, not line-based. "Doc Drift Detection in CI" article argues for CI placement (vs. local pre-commit) because "the developer who merged is not the person who wrote the docs."

### Schema/handoff testing

- **Schema-as-data-contract** is the lightweight prior art (e.g., dbt's contract enforcement: "when a model violates its declared contract, dbt errors with column-name and type-mismatch detail"). JSON Schema, OpenAPI, Pact are heavier alternatives.
- Convention-driven check (frontmatter declares producer/consumer) is the most cortex-native pattern.

### Citation parser: regex vs. AST

- For plain-prose `<file>:<line>` citations, **regex is correct**. AST parsing (mistune, markdown-it-py) buys nothing — citations tokenize as plain text, not structured nodes.
- AST is right for `[text](file#L10)` markdown-link form; cortex doesn't use that form.

### Anti-patterns from web research

- Don't snapshot trigger-phrase corpus (substring is the actual contract).
- Don't write size test against parsed/rendered skill (cap is on raw lines).
- Don't skip remediation hint in error message (point at progressive-disclosure to `references/`).
- Don't introduce per-skill exemptions for size cap unless a specific skill justifies it (Anthropic's recommendation is uniform).

## Requirements & Constraints

### `requirements/project.md` Architectural Constraints (load-bearing)

> "**SKILL.md-to-bin parity enforcement**: `bin/cortex-*` scripts must be wired through an in-scope SKILL.md / requirements / docs / hooks / justfile / tests reference (see `bin/cortex-check-parity` for the static gate). Drift between deployed scripts and references is a pre-commit-blocking failure mode. Allowlist exceptions live at `bin/.parity-exceptions.md`..." (project.md:29)

> "**Sandbox preflight gate**: ...The gate fails on missing/invalid preflight, stale `commit_hash`, or `claude --version` drift. This protects the per-spawn sandbox enforcement contract from silent regression on SDK pin bumps, function-name refactors, and CLI binary upgrades." (project.md:30)

These two clauses are the canonical precedents test #2 and test #3 pattern-match: **static, CI-time, drift-detection gates that fail pre-commit on contract regression**.

### `requirements/project.md` Quality Attributes

- "Quality bar: Tests pass and the feature works as specced. ROI matters."
- "Maintainability through simplicity: Complexity is managed by iteratively trimming skills and workflows. The system should remain navigable by Claude even as it grows." — directly justifies test #4 as enforcing "remain navigable."
- "Complexity: Must earn its place by solving a real problem that exists now." — applies to scoping; constrains scope creep.

### `CLAUDE.md` self-imposed cap (structural precedent for test #4)

> "CLAUDE.md is capped at 100 lines. Any policy entry — including this current edit — that would push CLAUDE.md past 100 lines must instead extract ALL existing policy entries (OQ3, OQ6, plus the new entry) into a sibling `docs/policies.md`, leaving CLAUDE.md with a one-line pointer..."

This is a **size-budget rule with explicit overflow contract** baked into the document itself. Pattern-matches test #4: a budget plus a documented remediation (extract to a sibling).

### Parent epic sanction (audit.md "Test gaps (new class)")

`research/vertical-planning/audit.md:282-290` enumerates exactly five test gaps:

1. No description-triggering snapshot tests
2. No cross-skill handoff integration tests
3. No description false-positive tests
4. No reference-file-cited path tests
5. No skill-size budget test

**#181 absorbs items 1, 2, 4, 5.** Item 3 (false-positive tests, "given input X, skill Y should NOT trigger") is sanctioned but **explicitly out of #181 scope** — a sanctioned-but-deferred sibling concern.

### Vertical-planning structure for test files (Considerations §2)

`research/vertical-planning/research.md` and the parent epic frame vertical-planning adoption as a `plan.md`/`spec.md` artifact-template change (Stream F = ticket #182), **not a test-layout change**. No instruction in the research argues that the four test files should adopt vertical-planning structure. **Conventional pytest layout (sibling files in `tests/`) is correct.**

### Out-of-scope and deferred

- "Application code or libraries — those belong in their own repos" — tests must remain skill-specific, not generalize to arbitrary application code.
- "events.log per-event consumer audit + 2-tier scheme" (parent epic deferred) — test #2 must not assume a future 2-tier event log.
- Doc-ownership: tests do not require updates to `docs/internals/*` — CLAUDE.md "NEVER proactively create documentation files" applies.

## Tradeoffs & Alternatives

For each design fork, the body presents A/B options; the **Recommended** column is the body's preferred default for spec.

### Fork A — File layout

| Option | Pros | Cons |
|---|---|---|
| **A1: Four separate test files** (Recommended) | Matches one-concern-per-file convention (`test_skill_callgraph.py`, `test_skill_contracts.py`, etc.); failure isolated per-file | Four near-identical SKILL.md enumerators (mitigated by `conftest.py` shared fixture) |
| A2: Single `test_skill_design.py` with parametrized cases | Shared fixtures, single skill enumerator | Loses one-concern-per-file convention; large file |
| A3: Extend existing `test_skill_callgraph.py` | Reuses existing pattern | Mixes runtime-callgraph concern with static-design concerns |

### Fork B — Skill enumeration

| Option | Pros | Cons |
|---|---|---|
| **B1: Filesystem glob `skills/*/SKILL.md`** (Recommended) | Zero maintenance; matches every existing test; auto-covers new skills | Silently passes for malformed skill |
| B3: Closed-set allowlist + glob self-test | Explicit; matches `cortex-check-parity` `PLUGIN_NAMES` pattern | Friction on new-skill add; second source of truth |

### Fork C — Citation parser (test #3)

| Option | Pros | Cons |
|---|---|---|
| **C1: Regex with fenced-code stripping** (Recommended) | Stdlib-only; matches `test_lifecycle_references_resolve.py` precedent | Edge cases: citations inside fenced code, prose worked examples |
| C2: AST-based (mistune / markdown-it-py) | Cleanly skips fenced code | Non-stdlib dependency; AST adds nothing for plain-text citations |

### Fork D — Size budget design

| Option | Pros | Cons |
|---|---|---|
| **D1: Uniform 500-line cap** (Recommended — matches Anthropic guidance literally) | Simple; aligned with skill-creator framework | `diagnose` at 489 leaves only 11 lines headroom — test #4 will fire near-immediately |
| D1+D4: Uniform 500 + per-skill `<!-- size-budget-exception: rationale ≥30 chars, lifecycle-id, YYYY-MM-DD -->` marker | Friction-with-escape-hatch | Requires marker convention learning |
| D2: Per-skill caps in fixture YAML | Realistic ceilings | Encodes current bloat; every legitimate growth requires cap edit |
| D3 (raise cap to 600): | Buffer for `diagnose` | **Rationalized bloat** — drifts up to accommodate state; contradicts Anthropic guidance |

**Recommendation: D1 — hold cap at 500.** If `diagnose` breaches during normal evolution, the breach is the signal for an extraction PR (exactly what test #4 is supposed to surface). D4 marker available as the escape hatch for genuine exceptions (≥30-char rationale, lifecycle id, date) — same shape as `bin/.parity-exceptions.md`.

### Fork E — Description-corpus shape (test #1)

| Option | Pros | Cons |
|---|---|---|
| E1: Hard-coded phrase list per skill in test | Maximum simplicity | Test diff + SKILL.md diff in two places per phrasing tweak |
| **E2: Declarative `tests/fixtures/skill_trigger_phrases.yaml`** (Recommended) | Single source of truth; phrasing changes land as one yaml diff next to SKILL.md diff | Indirection cost |
| E3: Snapshot-based (full description) | Catches any drift | Fails on legitimate prose tweaks; high false-positive rate |

### Fork F — Handoff field validation (test #2)

| Option | Pros | Cons |
|---|---|---|
| **F1: Declarative `tests/fixtures/skill_handoff_schema.yaml` field-name presence** (Recommended) | Static; declarative; matches user's STATIC scoping | Catches RENAME only, NOT semantic drift (see Adversarial §2) |
| F2: Parse SKILL.md prose for "writes X / reads X" patterns | Auto-discovers handoff fields | False-positive rate too high (path strings vs. field names) |
| F3: Generated schema doc | Authoritative | No such doc exists; out of scope |

### Fork G — Failure-message format

- **G2 Recommended**: `Violation`-dataclass output, `path:line:col: CODE message` format, optional `--json`, exit-code semantics matching `bin/cortex-check-parity`. Each test produces a clear, actionable error with **remediation hint** (e.g., "skill `diagnose` exceeds 500-line cap; consider extracting to references/ or add `<!-- size-budget-exception: ... -->` marker").

### Fork H — Test invocation

- **H3 Recommended**: pytest collected (auto via `tests/`) + new `just test-skill-design` recipe + wired into `test-skill-contracts` and `test-skills` aggregators. Matches existing skill-test pattern.

### Fork I — Failure-tier handling

- **I1 Hard-fail recommended over I3 (separate allowlist file).** Use the D4 in-file `<!-- size-budget-exception: ... -->` marker for test #4 exceptions; rely on the test #1 fixture YAML diff process to surface description-trigger updates. **Defer creating a `tests/.skill-design-exceptions.md` allowlist** until proven necessary by a real exception case (see Adversarial §3).

### Should we build a consolidated `bin/cortex-check-skill-design` CLI tool?

**Recommendation: NO.** The Tradeoffs agent recommended this; the Adversarial agent flagged it as scope creep. The four tests are pure pytest — they don't need pre-commit invocation outside of `pytest` since `just test` already runs them. Reserve `bin/cortex-check-*` for tools that need to run *outside* pytest. Consolidating shared helpers in `tests/conftest.py` or `tests/_skill_helpers.py` (test-side, not bin/-side) achieves DRY without spawning a 500-line tool that will accrete edge cases over quarters.

## Adversarial Review

### Major findings

**1. Test #3 corpus is empirically near-empty in `skills/**/*.md` scope.**
Of 8 `<file>:<line>` matches in `skills/`: 6 are fake worked-example prose (`client.py:142`, `auth.py:88`, `cache.py:55`, `migrate.py:212` in `critical-review/SKILL.md`; `src/foo.py:42`, `src/bar.py:18`, `src/baz.py:88` in `discovery/references/research.md`); only 2 are real (sibling pointers in `discovery/references/decompose.md`). The audit's example "`plan.md:107` references `critical-review/SKILL.md:176-182`" describes citations living in **`lifecycle/{slug}/plan.md`**, not skills/. **Test #3 as scoped to `skills/**` defends 2 real citations against 6 false-positives needing suppression — anti-leverage.**

**2. Test #2 (static schema) catches RENAME but NOT semantic drift.**
Real handoff regression mode is silent semantic decoupling: producer writes `discovery_source: research/{topic}/research.md`, consumer reads it expecting `research/{topic}/` directory — both fields exist with the same name but disagree on shape. Static name-presence YAML cannot detect this. Worse, expanding the fixture YAML to encode value-shape creates a 3-way drift trap (producer / consumer / fixture).

**3. The 600-line cap (Tradeoffs agent's recommendation) rationalizes bloat.**
Anthropic's literal guidance is ≤500. Setting the cap at 600 because `diagnose` is at 489 telegraphs that the cap is soft and drifts up. The right move when corpus is cap-adjacent is **extract**, not raise. Recommendation: hold at 500; D4 marker for genuine exceptions.

**4. Allowlist proliferation is a meta-failure mode.**
Each lint tool tends to ship its own allowlist file. Within 2-3 more lint tools, there's `bin/.parity-exceptions.md` + `tests/.skill-design-exceptions.md` + ... — schema sprawl, review burden, asymmetric incentive (adding to allowlist is cheaper than fixing root cause).

**5. Test #1 conflates regression vs. legitimate phrasing tweak.**
Audit identified 4/13 skills need description fixes in #178. Test #1 will fail on legitimate edits AND regressions, training developers to mechanically update the corpus fixture rather than evaluate "is this trigger removal intentional?"

**6. Surface-area-additive in tension with parent epic densification theme.**
Parent #172 is fundamentally a **removal** effort (~700 lines of cross-skill duplication targeted). Adding a 500-line lint tool + 4 test files + 2 fixture files + 1 allowlist + 1 justfile recipe is meta-irony. Mitigation target: ≤300 lines of new test code total, no new lint tool, no new allowlist file, 1 justfile recipe.

**7. Path-traversal safety in test #3.**
Naive regex `(\S+):(\d+)` over markdown can match `../../etc/passwd:1` in prose. Even though test runner already has read access, surface is surprising. **Mitigation: resolve cited paths to absolute, check `is_relative_to(REPO_ROOT)`, reject `..` segments.**

**8. Plugin-mirror false-pass and non-cortex-core plugins.**
Plugins outside cortex-core (`cortex-overnight`, `cortex-ui-extras`, `cortex-pr-review`, `android-dev-extras`, `cortex-dev-extras`) have hand-maintained SKILL.md outside the canonical→mirror flow. Test #4 either skips them entirely (uncapped growth) or includes them (different content profiles). **Explicit scope decision needed (see Open Questions).**

### Assumptions that may not hold

- Trigger phrases stable enough to gate → **counter**: 4/13 are in flux per #178.
- Handoff schema encodable as field-name presence → **counter**: actual handoff is value-shape (path-vs-slug, file-vs-directory).
- Line-anchored citations matter in skills/ → **counter**: 0 of 8 are real load-bearing references.
- 500 vs. 600 cap is content-density question → **counter**: it's a policy question (extract or accept).
- Test #1 fails closed → **counter**: fails open mostly on legitimate description edits.

### Recommended mitigations (consolidated)

1. **Re-scope test #3** to extend `tests/test_lifecycle_references_resolve.py` with the `<file>:<line>` form (where citations actually live) — OR drop test #3 from skills/** scope entirely. Do NOT build a parallel skill-scoped citation scanner for a 2-citation corpus.
2. **Re-scope test #2** to field-name presence ONLY with explicit docstring noting it does NOT catch semantic drift; consider deferring entirely if real coupling matters.
3. **Refuse the consolidated `bin/cortex-check-skill-design` lint tool.** 4 test files (or fewer if tests #2 and #3 fold elsewhere), shared helpers in `tests/conftest.py` only.
4. **Hold the cap at 500.** Per-skill in-file marker for exceptions; global cap raise rejected.
5. **Add a CHANGELOG `### Skill descriptions` section** for trigger-phrase corpus updates so changes are reviewable rather than mechanical.
6. **Path-resolve safety**: any path-from-prose lookup checks `is_relative_to(REPO_ROOT)` and rejects `..`.
7. **Document test scope explicitly in each test's docstring** with anti-expansion guidance.
8. **Total budget**: ≤300 lines of new test code, 0 new bin tools, 0 new allowlist files, 1 justfile recipe.

## Open Questions

### Resolved at Research exit gate

1. **Test #3 scope** (Adversarial §1): **Resolved — Extend `tests/test_lifecycle_references_resolve.py`** to add the `<file>:<line>(-<lend>)?` citation form. Do NOT build a parallel skill-scoped scanner. The 2 real citations in `skills/discovery/references/decompose.md` may be incidentally covered if the lifecycle resolver's globbing is extended to include `skills/**/*.md`, but the primary surface (where the audit's real example lives) is `lifecycle/{slug}/plan.md` — that's where the resolver already operates. Drops `tests/test_skill_reference_paths.py` from the spec; replaces it with a focused extension of the existing test.

2. **Test #2 scope** (Adversarial §2): **Resolved — Keep as static name-presence with explicit limitation**. Build `tests/test_skill_handoff.py` (or extend `test_skill_callgraph.py` if cleaner — spec to decide) using a declarative `tests/fixtures/skill_handoff_schema.yaml`. Test docstring must explicitly state: this test catches FIELD RENAMES (e.g., `discovery_source → research_source`); it does NOT catch semantic drift (e.g., field exists in both with different value-shapes). Anti-expansion guidance in docstring: do not expand fixture YAML to encode value-shape rules — that creates a 3-way drift trap.

3. **Skill-size cap** (Adversarial §3): **Resolved — 500 with in-file `<!-- size-budget-exception: ... -->` marker**. Hold Anthropic's literal guidance. If `diagnose` (currently 489) breaches during normal evolution, that breach is the signal for an extraction PR — exactly what test #4 is supposed to surface. Marker schema: `<!-- size-budget-exception: <reason ≥30 chars>, lifecycle-id=<NNN>, date=<YYYY-MM-DD> -->` (modeled on `bin/.parity-exceptions.md` schema).

4. **Non-cortex-core plugin SKILL.md scope** (Adversarial §8): **Resolved — All hand-maintained SKILL.md** (uniform 500 cap applies everywhere). Test #4 globs canonical `skills/**/SKILL.md` AND `plugins/*/skills/**/SKILL.md`. The dual-source byte-parity gate handles cortex-core mirror equality automatically. Per-plugin overrides via the same in-file marker (no separate per-plugin cap fixture).

### Deferred to Spec phase

5. **Allowlist creation** — defer to Spec: decide whether `tests/.skill-design-exceptions.md` should exist on day one or be deferred until a real exception case forces its creation. Research recommendation: defer; rely on D4 in-file markers for size budget and on the YAML fixture diff process for description/handoff updates. Spec to confirm or override.

6. **Test #1 fixture freshness contract** — defer to Spec: decide whether trigger-phrase corpus updates require a labeled CHANGELOG entry, a commit-message convention (`description-trigger:`), or no special process beyond standard PR review. Adversarial flagged the risk that without a review-affordance, fixture-update PRs become mechanical bypass. Spec to specify.

7. **`bin/cortex-check-skill-design` consolidated CLI tool** — defer to Spec: confirm whether to refuse the consolidated tool (Research + Adversarial recommendation) and instead use 3 test files (test #1, test #2, test #4) plus an extension of `test_lifecycle_references_resolve.py` for test #3. The four checks are pure pytest; a separate CLI is justifiable only if external (pre-commit, ad-hoc) invocation is desired beyond `just test`. Spec to confirm.

## Considerations Addressed

- **Validate that #181 is a sanctioned sub-thread of parent epic #172's audit "Test or verification gaps (new class)" section**: **Confirmed** — `research/vertical-planning/audit.md:282-290` enumerates exactly the four test classes #181 absorbs (items 1, 2, 4, 5; item 3 description false-positive tests is sanctioned-but-deferred). Not a sibling concern that drifted into the same epic.
- **Assess whether the parent epic's vertical-planning-adoption theme implies the four new test files should themselves adopt vertical-planning structure**: **No** — vertical-planning adoption (Stream F = #182) targets `plan.md`/`spec.md` artifact templates only. Tests are not lifecycle features and don't pass through plan.md/spec.md. Conventional pytest layout (sibling files in `tests/`) is correct and matches every existing `tests/test_*.py` precedent.
- **Explore at least one alternative approach for each test class (complex+high implementation suggestions present)**: Done across nine forks (A–I) in Tradeoffs section. Adversarial review further challenged consolidated-tool, 600-cap, allowlist creation, and test #2/#3 scope.
- **Enumerate canonical cross-skill handoff fields that test #2 must validate**: Done in Codebase Analysis §"Empirical surveys" — backlog frontmatter (16 fields), lifecycle artifact filenames (10), events.log event types (9), index.md frontmatter (7), spec/plan section anchors (5).
- **Survey current SKILL.md sizes**: Done — `diagnose=489` is the cap-adjacent skill (not `lifecycle=380` or `critical-review=365` as the ticket body claims). Ticket body factually outdated; spec must be written against current state.
- **Survey current `<file>:<line>` citation patterns and counts in `skills/`**: Done — **8 total matches, 2 real, 6 false-positive prose worked-examples.** This invalidates the ticket body's premise that test #3 in skills/** scope defends a meaningful corpus and is the dominant Open Question.
