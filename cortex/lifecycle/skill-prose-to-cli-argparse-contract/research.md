# Research: Skill-prose to CLI argparse contract lint

## Codebase Analysis

### Files that will be created or modified

**New files:**
- `cortex_command/lint/contract.py` — main lint module (sibling of `cortex_command/lint/prescriptive_prose.py`)
- `bin/cortex-check-contract` — dual-channel bash wrapper (mirrors `bin/cortex-check-parity`)
- `bin/.contract-lint-exceptions.md` — markdown table exception allowlist
- `tests/test_check_contract.py` — fixture-based parametrized test suite
- `tests/fixtures/contract/valid-*`, `invalid-*`, `exclude-*` — mini-repo fixtures
- `cortex/lint/contract-surface.json` (only if the derived-artifact requirement survives Spec — see Open Question OQ-1) — canonical enumeration of `(binary, subcommand, flag-set)` tuples

**Modified files:**
- `.githooks/pre-commit` — add a new phase (Phase 1.6 is **already occupied** by shim presence enforcement; reserve a phase number that does not collide, e.g., 1.55 or 1.86, after re-reading the hook)
- `justfile` — add `check-contract *args:` and `check-contract-audit:` recipes
- `skills/morning-review/SKILL.md:91`, `skills/backlog/SKILL.md:62`, `skills/discovery/SKILL.md:87` — add `--status` and `--type` to `cortex-create-backlog-item` invocations
- `skills/discovery/SKILL.md:77` — replace `python3 -m cortex_command.discovery generate-brief` with `cortex-discovery generate-brief` (subject to OQ-3: whether this is in scope)
- Multiple modules under `cortex_command/**` — refactor parser construction out of `main()` into a separable `build_parser()` factory (the pre-condition); see Open Question OQ-4 for the affected-module count

### Existing patterns to mirror

- **Sibling lint structure**: `cortex_command/parity_check.py` — stdlib-only, `tomllib` for `[project.scripts]`, file-corpus iteration, allowlist with categorical schema, `--staged` mode, `--json` output, `--self-test` mode. The contract lint should sit at this same shape.
- **Lint sub-package**: `cortex_command/lint/prescriptive_prose.py` — the lint sub-package is the right home for the new module. Its fence state machine (lines 113-156) is more reliable than `parity_check.py`'s `FENCED_CODE_RE`.
- **Wrapper script pattern**: `bin/cortex-check-parity:1-35` — dual-channel (try wheel import first, fall back to working-tree via PYTHONPATH); invokes `cortex-log-invocation` shim for telemetry; propagates argv directly.
- **Allowlist schema**: `bin/.parity-exceptions.md` — markdown table, 5 columns: `script | category | rationale | lifecycle_id | added_date`. Rationale ≥30 chars; forbidden literals enforced.
- **Test fixture pattern**: `tests/test_check_parity.py:34-90` — parametrized over `tests/fixtures/parity/valid-*|invalid-*|exclude-*` mini-repos, asserts JSON violation array shape.
- **Justfile recipe pattern**: lines 349-389; lowercase dash-separated recipe names, `*args` passthrough, audit-variant suffix.

### Integration points and dependencies

- **`[project.scripts]` table** (pyproject.toml lines 21-57): ~33 declared console scripts. Canonical source of named-binary → module mapping the lint introspects.
- **Active drifts (canonical list per backlog + research artifact)**: 4 named in ticket; **8 distinct drift signatures across ≥9 skill files** per `cortex/research/harness-friction-triage/research.md`.
- **Telemetry side-effect**: `cortex_command/backlog/_telemetry.py:73-142` — `log_invocation()` writes filesystem state and shells to git. If the lint imports a module to introspect its parser AND the parser is built inside `main()` (e.g., `create_item.py`), the telemetry call fires. AST-extraction sidesteps this entirely (see Adversarial Review S1/M2).
- **Pre-commit hook integration**: `.githooks/pre-commit` already has Phase 1.5 (parity), Phase 1.6 (shim enforcement — **occupied**), Phase 1.8 (events registry), Phase 1.85 (prescriptive prose). The contract lint needs a fresh phase number; 1.55 or 1.86 are the safe slots.
- **Existing pre-commit cost baseline**: parity check ~300ms; new lint adds 60-200% (~200-500ms) depending on AST vs import strategy.

### Conventions to follow

- Naming: `cortex-check-contract` (parallel to `cortex-check-parity`, `cortex-check-events-registry`, `cortex-check-prescriptive-prose`).
- Module location: `cortex_command/lint/contract.py`.
- Mutually exclusive `--staged` / `--audit` modes (two-mode gate pattern).
- Exit codes: 0 clean, 1 violations, 2 configuration error.
- Error format: `<path>:<line>:<col>: <CODE> <message>` (mirrors `parity_check.Violation.format_text()`).
- Backlog item closure via the normal lifecycle.

## Web Research

### Argparse introspection

- **Factory-function pattern** (`build_parser() -> ArgumentParser`) is the canonical exposure across `sphinx-argparse`, `argparse-manpage`, and `argcomplete`. Constructing the parser inside `main()` is the anti-pattern — testability and introspection both want the split.
- **Introspection mechanics**: `parser._actions` (Action objects exposing `option_strings`, `dest`, `choices`, `required`, `nargs`) and `parser._subparsers.choices` (`OrderedDict[name -> sub-ArgumentParser]`). Leading-underscore but de facto API — used by all the above libraries. Stability has been good across Python versions but is not contractual.
- **Side-effect risk**: parser construction is officially side-effect-free; the risk surfaces when projects construct their parser inside `main()` and `main()` reads env vars or hits the filesystem.
- **Entry-point discovery**: `importlib.metadata.entry_points(group="console_scripts")` returns `EntryPoint` objects you can `.load()`. Combined with a factory-function convention, this gives clean introspection without running `main()`.
- **AST-based alternative**: `sphinx-argparse` and `argparse-manpage` support AST extraction (read source, find `argparse.ArgumentParser(...)` constructor + `.add_argument(...)` calls, build a static representation). Avoids import-time side effects and Python-version private-API coupling.

### Documentation/contract drift linters

- **Drift (Fiberplane)**: closest analogue. Anchors in markdown reference source files+symbols; retrospective comparison against git history. Acknowledged limitation: detection ≠ compliance — relies on CI + reviewer discipline.
- **OpenAPI ecosystem** (Spectral, oasdiff, Schemathesis): well-developed contract-drift tooling, but the source-of-truth direction (spec drives implementation) is opposite to the cortex linter (CLI drives prose).
- **Doctest-style**: `cargo test --doc` (Rust), `sybil`, `pytest-codeblocks`, `markdown-clitest`. Execute fenced blocks; none validate against a CLI surface directly.
- **`mkdocs-click`**: generates docs FROM Click introspection — drift impossible by construction, at the cost of prose-style constraint.

### Pre-commit hook patterns

- `pre-commit` framework: exit non-zero blocks; `--files` passes staged file list; machine-readable stdout.
- `lint-staged` (JS): ~3x speedup from staged-only vs whole-tree.
- Ruff/mypy pragma vocabulary: `# noqa: <code>` (inline), per-file ignores in `pyproject.toml`. Ruff specifically preserves unknown rule codes in noqa for forward-compat.
- `golangci-lint` baseline pattern: record current violations on first run, only report new ones thereafter. Worth considering if legacy drift surface is large.

### Regex tolerance / extraction from prose

- **Markdown parsing**: `markdown-it-py` (token-based, distinguishes fenced vs inline) and `mistune` (full AST with `block_code`/`codespan` nodes) are the standard recommendation. Pure regex parsing is fragile under nested fences, indented blocks, tilde fences, and info strings.
- **Command tokenization**: `shlex.split(comments=False)` is the workhorse; wrap in try/except for malformed quotes. Does NOT understand line continuations or templated placeholders (`{{var}}`, `{value}`, `<slug>`) — those need separate handling.

### False-positive governance

| Approach | Pros | Cons |
|---|---|---|
| Inline pragma (Ruff `# noqa`) | Locality | Pollutes prose; survives indefinitely without revisit |
| File-based exception list (golangci, mypy per-file) | Centralized review; visible in code review | Drift between list and actual mentions; "set and forget" risk |
| Structured baseline (golangci baseline mode) | Fail only on new violations | Requires regeneration discipline; can hide regressions |

For the cortex case: a structured exemption file plus a CI check that fails when entries no longer match any prose location catches the "exemption became stale" problem.

### Performance

- Staged-only mode is the standard win.
- Markdown parsing is the dominant per-file cost.
- Argparse introspection cost is paid once per linter invocation if cached.
- Cold-import cost across 33 entry-point modules measured at ~500ms under `uv run`; import without project venv fails on missing `yaml`.

### Key external sources

- Python argparse, sphinx-argparse, argparse-manpage, argcomplete docs
- importlib.metadata entry_points spec
- Drift (Fiberplane) documentation linter
- markdown-it-py, mistune, shlex docs
- ruff settings, golangci-lint false-positives & baseline docs
- pytest-codeblocks, sybil, markdown-clitest, mkdocs-click

## Requirements & Constraints

### From cortex/requirements/project.md

- **SKILL.md-to-bin parity enforcement**: `bin/cortex-*` scripts wire through SKILL.md/requirements/docs/hooks/justfile/tests reference surfaces. `bin/cortex-check-parity` blocks file-level drift; exceptions at `bin/.parity-exceptions.md`. The new lint sits **at lower altitude (argument-level)** as a sibling, not as an extension.
- **Skill-helper modules pattern**: New skill-helper modules collapse SKILL.md dispatch into atomic `cortex_command/<skill>.py` subcommands. Expose via `[project.scripts]` (e.g., `cortex-<skill>`) as recommended invocation; `python3 -m cortex_command.<skill>` is the readable fallback. New events register in `bin/.events-registry.md`.
- **Two-mode gate pattern** (Optional section): pre-commit gates pair `--staged` (diff schema) with `--audit` (time/repo-wide, `just <recipe>-audit`). Encouraged, not mandated. Example: `bin/cortex-check-events-registry`.
- **Wheel-binstub vs working-tree invocation**: `cortex-<skill>` binstubs execute against installed wheel's `site-packages/`; `python3 -m cortex_command.<skill>` runs against the working tree. `CORTEX_COMMAND_FORCE_SOURCE=1` forces working-tree.
- **Solution horizon**: long-term project — fixes reflect that. A scoped phase of a multi-phase lifecycle is not a stop-gap. Anchor on current knowledge, not prediction.
- **MUST-escalation policy**: prefer soft positive-routing phrasing for new authoring.

### Parity exception allowlist schema

`bin/.parity-exceptions.md`: 5-column markdown table.
- `script`: matches `cortex-[a-z][a-z0-9-]*`, bare token.
- `category`: enum — `maintainer-only-tool`, `library-internal`, `deprecated-pending-removal`.
- `rationale`: ≥30 chars after trim; forbidden literals (case-insensitive): `internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary`.
- `lifecycle_id`: ticket that introduced the entry.
- `added_date`: `YYYY-MM-DD`.

The contract lint's exception file should mirror this schema but with column meanings adapted to argument-level violations (e.g., `binary | flag-or-subcommand | category | rationale | lifecycle_id | added_date`).

### Events registry

`bin/.events-registry.md`: 11-column schema (`event_name | target | scan_coverage | producers | consumers | category | added_date | deprecation_date | rationale | owner`). If the contract lint emits new events (e.g., `contract_lint_run`, `contract_drift_detected`), they must register here.

### Architecture Decision Records

- **ADR-0001 (File-based state)**: cortex stores state as markdown/JSON/YAML files; rejects database approach.
- **ADR-0002 (CLI wheel + plugin distribution)**: two-channel distribution; coupled by versioned envelope.
- **ADR-0003 (Per-repo sandbox registration)**: `cortex init` additively registers repo's `cortex/` umbrella.
- **DR1** (from harness-friction-triage research): lint-driven parity over manifest-driven generation. **Vetoes manifest-based approaches** (cucumber-style YAML/TOML CLI surface, schema-first parser generation).

### Parent epic and consumer

- **Epic #251** ("Harness friction triage: distribution, contracts, slugs, gates"): tracks five children; epic body states children "can ship in any order; they do not depend on each other for correctness," with one shared input surface (the skill-prose grep enumeration owned by #253, consumed by #252's PATH self-test).
- **#252 status**: complete. Adversarial review (F10) verified `cortex_command/doctor/path_self_test.py` sources its binary list from `importlib.metadata.entry_points()`, **NOT** from a 253-produced artifact. See OQ-1.

### Drift surface (canonical, from research artifact)

8 distinct drift signatures across ≥9 skill files — more than the 4 named in the ticket. The expanded surface includes `cortex-update-item`'s `key=value` form (which has no argparse parser to validate against) and path-qualified `bin/cortex-*` invocations.

## Tradeoffs & Alternatives

### Approaches evaluated

**A. Regex-grep prose → import-introspect argparse (ticket's design)**
- Pros: reuses `[project.scripts]` table; exact validation; deterministic; offline; mirrors `prescriptive_prose.py` shape; ~400 LOC stdlib-only.
- Cons: pre-condition that every targeted module exposes `build_parser()` is **larger than the ticket suggests** (19 of 33 modules need refactoring; some don't use argparse at all). Module-import side effects (telemetry, SDK import, yaml import) fire on every lint run unless guarded or avoided.

**B. Subprocess `--help` parsing**
- Pros: no Python import dependency; uniform across argparse/click/typer; isolates side effects.
- Cons: slow (~50ms × 36 binaries = ~2s added to every pre-commit). `--help` output format is not a stable contract; argparse changes between Python minors. Misaligned with existing tomllib + filesystem pattern.

**C. In-place extension of `cortex-check-parity`**
- Pros: maximum code reuse (fenced-code parsing, allowlist governance, staged-blob retrieval, `--lenient`/`--json`/`--self-test` machinery).
- Cons: ticket explicitly vetoes ("do not extend in-place"); defensible because file-level and argument-level have different change rates and exception schemas; W005-style "allowlist-superfluous" mechanic doesn't transfer to argument level.

**D. Doctest-style executable examples**
- Pros: zero false positives by construction.
- Cons: requires safe dry-run mode on every CLI (most don't have one); subprocess-per-invocation cost; reshapes prose authoring.

**E. Cucumber-style executable spec (YAML/TOML manifest)**
- Pros: reviewable in code review.
- Cons: adds a third source of truth — the very drift the lint exists to prevent. Violates DR1 (lint-driven parity over manifest-driven generation).

**F. Schema-first parser generation**
- Pros: drift impossible by construction.
- Cons: requires rewriting all ~36 modules' parser construction. Out of scope for this lifecycle.

### Recommended approach: A with explicit pre-condition and AST-extraction variant

Approach A is correct for this lifecycle, **but the adversarial review reframes the implementation strategy**: AST extraction (read each module's source, find `argparse.ArgumentParser` constructor + `.add_argument(...)` calls statically) is preferable to runtime module import because it avoids:
- Module-import side effects (`_telemetry.log_invocation`, `claude_agent_sdk` import, `yaml` import)
- Pre-commit-shell venv dependency
- ~500ms cold-import cost
- Confused-deputy risk for any future third-party `[project.scripts]` entries
- Python-version coupling to private `_actions`/`_subparsers` API

The factory-function pre-condition (`build_parser()`) is **only required** if runtime import is the strategy. AST extraction relaxes the pre-condition to "the parser is constructed via `argparse.ArgumentParser` and `.add_argument`" — which most modules satisfy already (excepting the `key=value`-shaped `update_item.py` and other hand-rolled argv parsers).

### Sub-decisions within recommended approach

- **Code-fence awareness**: REQUIRED. Use the existing `cortex_command/lint/prescriptive_prose.py:113-156` fence state machine, not `parity_check.py`'s `FENCED_CODE_RE` (which is fragile under tilde fences, indented blocks, and info-string variants). Even better: depend on `markdown.extensions.fenced_code` (already in pyproject deps).
- **Exception governance**: File-based at `bin/.contract-lint-exceptions.md`, mirroring the parity-exceptions schema with columns adapted for argument-level violations. Plus a self-check that fails when entries no longer match any prose location (catches stale exemptions). Optionally a sentinel inline marker (`<!-- contract-lint:ignore-next -->`) for migration notes — open question, see OQ-2.
- **Artifact format and location**: TBD pending OQ-1. If the artifact is preserved, JSON at a path within `cortex/lint/` so #252 (or human/external audit consumers) can read it structurally. If OQ-1 resolves to "no consumer," drop the artifact requirement entirely.
- **Drift batching / landing strategy**: User's clarify-phase decision was "fix existing drift in same PR + enable as hard block." Adversarial review (A4/M10) flags that this assumes only 4 drift callsites, which holds for the `cortex-create-backlog-item` flag fixes but does not hold once `cortex-update-item`'s `key=value` form is in scope. See OQ-5.

## Adversarial Review

The full adversarial pass surfaced material failure modes. The highlights below drive the Open Questions section below; see OQ-1 through OQ-6 for the unresolved items the Spec must address.

### Failure modes

- **F1 / 19-module refactor**: only ~14 of 33 `[project.scripts]` modules expose a separable parser; the rest build it inline in `main()` or — for `update_item.py`, `state_cli.py`, `worktree_resolve_cli.py`, `interrupt.py`, `log_invocation.py`, `common.py` — don't use argparse at all. `update_item.py` uses `key=value` positional pairs (tracked for a syntax refactor by backlog #257). The lint cannot validate `cortex-update-item status=complete` against an argparse parser that does not exist.
- **F2 / Import side-effects**: `_telemetry.log_invocation()` is not the only hazard; transitive imports pull in `claude_agent_sdk`, `yaml`, `logging`, and compiled regexes. The lint should not rely on runtime import.
- **F3 / Argparse introspection edge cases**: mutually-exclusive groups, `argparse.SUPPRESS` help, `required=True` subparsers, custom Action classes, exotic `nargs`. `_actions` walking is incomplete by default.
- **F4 / Subcommand resolution from prose**: shell substitutions (`$(cortex-foo)`), pipes, templated placeholders (`{{type}}`, `{value}`, `<slug>`), positional-vs-flag ambiguity. Requires positional-vs-flag classification per binary.
- **F5 / Fence regex weakness**: `parity_check.py:436`'s `FENCED_CODE_RE` doesn't handle tilde fences, indented blocks, or info-string variants. Use the prescriptive-prose state machine or a markdown parser.
- **F6 / Archive corpus false positives**: 42+ files under `cortex/research/archive/**` reference retired commands; `CHANGELOG.md` documents removed commands as historical record; `bin/.audit-bare-python-m-allowlist.md` itself enumerates the syntax being retired. Scope-glob hardening required.
- **F7 / `python3 -m cortex_command.*` retirement**: this syntax is being phased out by a separate audit gate (`bin/.audit-bare-python-m-allowlist.md`); the contract lint validating it would double-police with potentially contradictory verdicts.
- **F8 / Performance**: importing 33 modules costs ~500ms under `uv run` and fails outright with system Python. The lint should AST-extract or invoke through `uv run`.
- **F9 / Self-application bootstrap**: the lint's own skill prose mentions `cortex-check-contract`; needs first-run bootstrap.
- **F10 / Artifact-consumer mythology**: #252 has shipped (status: complete) and sources its binary list from `importlib.metadata.entry_points()`, not from a 253-produced artifact. The "derived artifact for #252 to consume" requirement may be gold-plate. See OQ-1.
- **F11 / Migration-note false positives**: skills authored as before/after migration notes legitimately reference deprecated commands; needs a sentinel-comment escape hatch.

### Security concerns

- **S1 / Confused-deputy on import**: today modules are in-tree, but if `[project.scripts]` ever points to a third-party module (via plugin extension), runtime import executes third-party code at pre-commit time. AST extraction sidesteps this.
- **S2 / Hard-block wedge risk**: a false positive due to a markdown-parsing edge case blocks every commit until allowlisted. The parity check has been tuned over multiple lifecycles; the contract lint starts from zero.
- **S3 / Python-version coupling**: `_actions` is private API; AST extraction is more durable.

### Assumptions that may not hold

- **A1 / "Each module's parser is side-effect-free"** — holds for ~14 modules today; 19 need refactor or AST-extraction strategy.
- **A2 / "Skill prose mentions are well-formed invocations"** — fails for templated placeholders, partial commands, tabular rows, migration notes, historical entries.
- **A3 / "The artifact has a consumer"** — false; #252 already shipped without it.
- **A4 / "Hard-block in same PR will be cleaner than warning-then-block"** — defensible only if the drift surface is the 4 callsites the user assumed; not if `update_item` is in scope.
- **A5 / "Pre-commit Phase 1.6 is open"** — false; occupied by shim presence enforcement.
- **A6 / "`cortex/` files are in scope"** — `cortex/research/**` and `cortex/lifecycle/**` contain legitimate references to retired or deprecated invocations; scope must be explicit.

### Recommended mitigations (carried into Spec)

- **M1 / Narrow v1 scope** to: validate `cortex-create-backlog-item` invocations against argparse surface, scan `skills/**/*.md` only, defer the broader contract surface to follow-up lifecycles. Closes the named drifts and proves the mechanism without paying the 19-module-refactor cost.
- **M2 / AST extraction over runtime import**.
- **M3 / Reuse prescriptive-prose fence state machine**, not parity-check's `FENCED_CODE_RE`.
- **M4 / Hard-exclude archive/CHANGELOG corpus from scan globs**.
- **M5 / Sentinel comment for migration-note exceptions** (`<!-- contract-lint:ignore-next -->`).
- **M6 / Drop or rescope the derived-artifact requirement** (OQ-1).
- **M7 / Reserve a non-colliding pre-commit phase number**.
- **M8 / Drop `python3 -m cortex_command.*` from the lint's scope** — defer to the existing audit gate.
- **M9 / Tolerate `cortex-update-item` (and other key=value-shaped modules) via category-based exception** until backlog #257 lands argparse-style flag parsing.
- **M10 / Reconsider hard-block-same-PR landing** if the drift surface is wider than the 4 callsites the user assumed.

## Open Questions

All items have been resolved or explicitly deferred to Spec with rationale, per the Research Exit Gate.

- **OQ-1 (Artifact consumer is mythological)**: **Resolved — drop the artifact requirement from 253.** `cortex_command/doctor/path_self_test.py` (the supposed consumer) already shipped reading binaries via `importlib.metadata.entry_points()` directly, which is a stable public API that doesn't require an emitted artifact. The "Complexity must earn its place by solving a real problem now" principle vetoes designing for hypothetical future audit consumers. If a real consumer emerges, that lifecycle owns the artifact contract — not 253. The lint computes the canonical enumeration internally for its own validation but does not persist it.

- **OQ-2 (Escape hatch shape)**: **Deferred: spec will propose dual escape hatches** — file-based at `bin/.contract-lint-exceptions.md` (mirroring `.parity-exceptions.md`) for centralized governance, AND a sentinel inline marker (`<!-- contract-lint:ignore-next -->`) for migration notes that legitimately demonstrate deprecated invocations inline. The file-based ledger is the primary governance surface; the inline marker is a pragmatic affordance for cases where per-line allowlist entries would scale poorly.

- **OQ-3 (`python3 -m cortex_command.*` form)**: **Resolved — drop `python3 -m` validation from 253.** The audit gate (`bin/.audit-bare-python-m-allowlist.md` + `--audit-bare-python-m-callsites` in `parity_check.py`) already owns syntax retirement. The contract lint focuses on `cortex-*` console-script form only. The discovery skill's `python3 -m cortex_command.discovery generate-brief` drift moves out of 253's scope — it's a syntax-style drift (the audit gate's job), not a flag-contract drift. This reduces 253's named-drift coverage from 4 → 3 callsites (the three `cortex-create-backlog-item` invocations missing `--status`/`--type`).

- **OQ-4 (Pre-condition / refactor scope)**: **Resolved — use AST extraction, not runtime module import.** Reading each module's source via `ast`, finding `argparse.ArgumentParser(...)` construction and `.add_argument(...)` calls, and building a static surface. Avoids module-import side effects (`_telemetry.log_invocation`, `claude_agent_sdk` import, `yaml` import), avoids ~500ms cold-import cost, avoids pre-commit shell venv dependency, avoids confused-deputy risk for any future third-party `[project.scripts]` entries, and avoids Python-version coupling to private `_actions`/`_subparsers` API. This decision relaxes the factory-function pre-condition — modules don't need to expose `build_parser()` separately; they just need to use standard argparse calls.

- **OQ-5 (v1 scope narrowing)**: **Resolved — middle scope.** Validate all `[project.scripts]`-registered modules whose parsers are AST-extractable (i.e., they use standard `argparse.ArgumentParser` + `.add_argument` calls). Categorically exempt modules that don't use argparse (`update_item.py` `key=value` form, `state_cli.py` hand-rolled argv loop, `worktree_resolve_cli.py` single-positional, `interrupt.py`, `log_invocation.py`, `common.py`, etc.) via `bin/.contract-lint-exceptions.md` entries with rationale "module does not use argparse — pending lifecycle TBD" (or "pending #257 landing" for `update_item.py` specifically). Avoids the 19-module refactor and the #257 dependency. Closes the named `cortex-create-backlog-item` drift across 3 skills. Documents the exempted modules so they're trackable for future broadening lifecycles.

- **OQ-6 (Landing strategy revisit)**: **Resolved — Clarify decision holds (fix drift in same PR + hard block).** With OQ-5 resolving to middle scope and OQ-3 dropping `python3 -m`, the in-PR drift fixes are the three `cortex-create-backlog-item` callsites in `skills/morning-review/SKILL.md:91`, `skills/backlog/SKILL.md:62`, `skills/discovery/SKILL.md:87` — a tractable 3-line set of additions. The categorical exemptions for hand-rolled modules are documentation entries, not code refactors. Same-PR hard-block remains the right call.

- **OQ-7 (Scope-glob exclusions, explicit)**: **Deferred: spec will propose hard-excluding** `cortex/research/archive/**`, `CHANGELOG.md`, `bin/.audit-*-allowlist.md`, `bin/.parity-exceptions.md`, and `cortex/lifecycle/**` (completed lifecycle prose may reference deprecated invocations as historical record). Scan corpus is: `skills/**/*.md`, `hooks/**`, `justfile`, `docs/**/*.md`, `tests/**`, `CLAUDE.md`, `cortex/requirements/**/*.md`.

- **OQ-8 (Pre-commit phase slot)**: **Deferred: spec will propose Phase 1.55** (between parity 1.5 and shim 1.6) — chosen because parity is a logical prerequisite (the contract lint depends on `[project.scripts]` resolvability that parity validates), and 1.55 reads cleanly in the hook source.

- **OQ-9 (Argparse edge cases)**: **Deferred: spec will propose** covering `required=True` and `argparse.SUPPRESS`-helped flags in v1; deferring mutually-exclusive groups (`add_mutually_exclusive_group`), custom Action classes, and exotic `nargs` (`'?'`, `'*'`, `'+'`, `'REMAINDER'`) to a v1.5 follow-up lifecycle. The deferred edge cases produce false-negatives (lint accepts invocations the parser would reject), not false-positives (the failure mode is safer for an initial rollout).

- **OQ-10 (Two-mode `--staged`/`--audit`)**: **Deferred: spec will propose both modes from v1**, mirroring `cortex-check-events-registry`. `--staged` operates on the pre-commit diff; `--audit` operates on the full repo via `just check-contract-audit`.
