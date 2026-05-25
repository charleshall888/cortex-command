# Research: Fix test cascade from #252 migration (SourceFileLoader + subprocess patterns)

## Codebase Analysis

### Per-file pattern inventory

| Test file | SourceFileLoader on bin/* | `subprocess.run([…, str(SCRIPT_PATH), …])` on bin/* | Other | Promoted module(s) |
|-----------|---------------------------|------------------------------------------------------|-------|-------------------|
| `tests/test_resolve_backlog_item.py` | yes (~L122–129) | yes (L154, 720, 777) | — | `cortex_command.backlog.resolve_item` |
| `tests/test_load_parent_epic.py` | yes (~L423) | yes (L60, 373) | — | `cortex_command.backlog.load_parent_epic` |
| `tests/test_check_prescriptive_prose.py` | no | yes (L47, 56) | — | `cortex_command.lint.prescriptive_prose` |
| `tests/test_commit_preflight.py` | no | yes (L103–109) | — | `cortex_command.commit.preflight` |
| `tests/test_superseded_frontmatter_tolerance.py` | yes (L79) | yes (L108, 171, 187) | — | `cortex_command.backlog.{load_parent_epic, resolve_item}` |
| `tests/test_variant_a_writer_sites_baseline.py` | yes (L56–62) | yes (L292, 322, 355) | — | `cortex_command.lifecycle.complexity_escalator` |
| `tests/test_clarify_critic_alignment_integration.py` | no | yes (L98–103) | — | `cortex_command.backlog.load_parent_epic` |
| `tests/test_cortex_log_invocation_parity.py` | no | already correct `-m` form (L410) | `id(tmp_path)` cache-key hazard at L370 | `cortex_command.log_invocation` |
| `cortex_command/dashboard/tests/test_feature_cards_pr_url.py` | — | — | — | — (already clean) |
| `cortex_command/dashboard/tests/test_templates.py` | — | — | — | — (already clean) |

Two of the ten files named in the ticket (`test_feature_cards_pr_url.py`, `test_templates.py`) contain no `SourceFileLoader` or `bin/cortex-*` subprocess patterns. Their failure mode in the cascade is likely indirect (transitive ImportError when a sibling module's collection fails). Verify their failure mode mid-Implement after the eight direct-pattern files are fixed.

### Sibling `id(tmp_path)` hazard not named by the ticket

The same `cache_key = (id(tmp_path), case)` pattern exists at `tests/test_cortex_complexity_escalator_parity.py:168`. The ticket names only `test_cortex_log_invocation_parity.py:370`. Fixing only the named site leaves the sibling broken; the same patch shape applies to both.

### Canonical fix patterns (from Tasks 11/12/15 in #252)

**SourceFileLoader → direct import** (Task 15 model, `tests/test_complexity_escalator.py` commit 5f0d16eb):

```python
# Before
loader = importlib.machinery.SourceFileLoader("cortex_resolve_backlog_item", str(SCRIPT_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

# After
import cortex_command.lifecycle.complexity_escalator as _escalator_module
@pytest.fixture(scope="module")
def escalator_module():
    return _escalator_module
```

**Subprocess via `bin/cortex-X` → `-m` invocation** (Tasks 11/12 model on `_run_script` helpers):

```python
# Before
subprocess.run([sys.executable, str(SCRIPT_PATH), ...], ...)

# After
subprocess.run([sys.executable, "-m", "cortex_command.parity_check", "--json"], ...)
```

### Promoted-module readiness

All 13 promoted `cortex_command.*` modules carry `if __name__ == "__main__": main()` blocks and are wired in `pyproject.toml [project.scripts]`. The `python3 -m cortex_command.X` invocation works for every module touched by this ticket — no production-side edits required to support the `-m` path.

### Integration points

- `pyproject.toml [project.scripts]` — every promoted module has a console-script entry (`cortex-X`) so binstubs also work after `uv tool install --reinstall --refresh`, but tests should not depend on the installed wheel (working-tree fidelity).
- `bin/cortex-*` — dual-channel bash wrappers post-#252. Tests must not attempt to load these as Python.
- `tests/fixtures/` — golden-replay fixtures (`cortex-complexity-escalator/`, `cortex-check-parity/`, `cortex-log-invocation/`) assert byte-identical wrapper behavior; these are not affected by this ticket.
- `bin/.parity-exceptions.md` — three entries (`cortex-archive-sample-select`, `cortex-batch-runner`, `cortex-pipeline-metrics`); none affect the 10 files in scope.

### Conventions

- Import promoted code directly: `from cortex_command.X.Y import Z`, not `SourceFileLoader('mod', 'bin/cortex-X')`.
- For subprocess: prefer `[sys.executable, "-m", "cortex_command.X"]` over `[sys.executable, str(SCRIPT_PATH)]` (the latter points at a bash wrapper after #252).
- Cache-key paths: use `str(tmp_path)`, not `id(tmp_path)`.

## Web Research

### Direct import vs `SourceFileLoader`

`SourceFileLoader.load_module()` is deprecated in CPython and slated for removal. The canonical Python recommendation when a script has been promoted to an importable module is direct import — file-based loading exists only for code that genuinely lives outside any package. The pytest project explicitly recommends the `src`-layout-plus-install pattern (or `--import-mode=importlib`) so tests reference the installed/importable package, not files on disk.

Sources:
- pytest "Good Integration Practices" — <https://docs.pytest.org/en/stable/explanation/goodpractices.html>
- pytest import mechanisms — <https://docs.pytest.org/en/stable/explanation/pythonpath.html>
- Python bug tracker issue 43540 (importlib: document how to replace load_module) — <https://bugs.python.org/issue43540>

### `subprocess.run(['cortex-X', …])` (binstub) vs `[sys.executable, '-m', 'cortex_command.X', …]`

The dominant pattern across the pytest ecosystem (Click, pip, hatch test suites) is in-process or `python -m` invocation for the bulk of CLI tests, with a small number of installed-binstub smoke tests guarding the packaging surface. Binstub invocation requires `pip install -e .` (or full install) before tests and is sensitive to PATH/venv state; `-m` invocation guarantees the interpreter running the test is also running the subject-under-test. For cortex-command, where project.md line 38 explicitly endorses `python3 -m cortex_command.<skill>` as the working-tree-fidelity idiom, `-m` is the convention-aligned default.

Sources:
- Click — Testing Click Applications — <https://click.palletsprojects.com/en/stable/testing/>
- Python Packaging User Guide — entry points — <https://packaging.python.org/specifications/entry-points/>

### `id()` aliasing on pytest path fixtures

`id()` returns an integer unique only among objects with overlapping lifetimes; CPython recycles memory addresses after garbage collection. Comparing `id()` of pytest `tmp_path` objects across test invocations is unsafe — a new `Path` allocated at a recycled address will key-collide with a stale entry. The canonical Python anti-pattern guidance (charlax/antipatterns, multiple style guides): never write `id(x) == id(y)`; use `is` for identity or `==` for value equality. For pytest tmp_path, the path value (`str(tmp_path)` or `tmp_path.resolve()`) is the stable identity.

Sources:
- pytest tmp_path docs — <https://docs.pytest.org/en/stable/how-to/tmp_path.html>
- charlax/antipatterns — <https://github.com/charlax/antipatterns/blob/master/python-antipatterns.md>
- Python id() recycling explainer — <https://sqlpey.com/python/python-object-id-reuse/>

### Lint tooling that would catch this class of failure pre-merge

No off-the-shelf lint rule catches `SourceFileLoader('mod', 'bin/cortex-X').load_module()` or `subprocess.run(['bin/cortex-X', ...])` where the bin file is no longer importable Python:

- Vulture (dead-code finder) flags orphaned symbols but not stale string-path references.
- Ruff S404/S603 (subprocess rules) — S603 was relaxed in Ruff v0.12.0 to accept literal-string command lists, so the pattern that broke here is explicitly **not** flagged.
- pre-commit-hooks ships `destroyed-symlinks` and `check-executables-have-shebangs` but no "literal path in source must exist on disk" hook.

The established pattern for this kind of repo-specific invariant is a small custom pre-commit hook (~10–80 lines) that scans `tests/` for hardcoded `bin/cortex-*` literals and `SourceFileLoader` patterns whose second arg is no longer importable. Sphinx, devpi, and similar projects carry custom hooks for exactly this kind of check.

Source: Ruff v0.12.0 release notes — <https://astral.sh/blog/ruff-v0.12.0>

## Requirements & Constraints

### From `cortex/requirements/project.md`

**Skill-helper modules** (L35):
> "Promoted modules expose a `[project.scripts]` console-script entry (e.g. `cortex-<skill>`) as the recommended invocation idiom; `python3 -m cortex_command.<skill> <subcommand>` is retained as a readable fallback for ad-hoc invocation."

**Wheel-binstub vs working-tree invocation** (L38, abridged):
> "`cortex-<skill>` binstubs execute against the installed wheel's `site-packages/`; `python3 -m cortex_command.<skill>` runs against the working tree. … Use `python3 -m` invocation to run against the working tree when wheel reinstall between phases is not feasible. Setting `CORTEX_COMMAND_FORCE_SOURCE=1` in the environment makes the dual-channel wrappers in `bin/cortex-*` skip the wheel-import branch and execute the working-tree module directly. … Dogfooders iterating on working-tree code without `--reinstall` between edits should export this variable."

**Quality bar** (Philosophy of Work): "Tests pass; the feature works as specced." The closeout signal `just test` exits 0 (or down to the pre-existing `test_log_invocation_perf` failure) directly maps to this.

**Solution horizon** (Philosophy of Work): For a fix to be durable, it must not already be known to need redoing. The cascade pattern (promotion task forgets downstream tests) recurs only on future bin/* promotions; the bulk of promotable scripts have already been promoted in #252. The recurrence risk is shrinking, not growing — durable fix is "apply the canonical pattern" rather than "build a lint gate."

### From `bin/.parity-exceptions.md`

Two relevant library-internal entries: `cortex-batch-runner` (spawned by `cortex_command/overnight/runner.py`) and `cortex-pipeline-metrics` (in-process import by `cortex_command/hooks/scan_lifecycle.py`). Neither is among the 10 affected test files; no scope adjustment needed.

### From #252's lifecycle (`cortex/lifecycle/convert-bin-cortex-and-skill-embedded/events.log`)

#252 was overridden simple→complex and medium→high mid-flight ("affects shared skills and workflow infrastructure running inside autonomous Claude execution paths"). The lifecycle has only 5 recorded events; no explicit "test cascade" deferral was logged. The cascade is unrecorded undone work, not a deliberate deferral — which is what #261 documents.

### From `cortex/adr/0002-cli-wheel-plus-plugin-distribution.md`

The two-channel distribution model (non-editable CLI wheel + Claude Code plugins) means tests cannot assume binstubs are present without explicit `uv tool install --reinstall`. This reinforces the working-tree-fidelity argument for `-m` invocation in tests: binstubs may lag the working tree or be entirely absent on a fresh checkout.

### Scope boundaries

- Tests are in scope (project.md §3 In Scope: "tests").
- Promoted `cortex_command.*` modules are not modified — their `__main__` blocks already exist.
- Tests run against the working tree via `sys.executable -m`, not against the installed wheel (per the Wheel-binstub constraint).
- Two-channel distribution (ADR-0002) means binstubs cannot be assumed present without `uv tool install --reinstall`.

## Tradeoffs & Alternatives

### Alternative A — Per-file judgment (ticket's stated approach)

Each callsite picks its own pattern from {direct import, `-m`, binstub, bash-wrapper-as-executable}. Highest decision cost; risk of heterogeneous post-state.

- Implementation complexity: medium-high · Maintainability: medium · Performance: n/a · Alignment with project.md: high

### Alternative B — Uniform `[sys.executable, "-m", "cortex_command.X"]` for subprocess sites

Standardize every subprocess callsite to `-m` invocation; standardize every `SourceFileLoader` site to direct import. One pattern across all repaired files. Project.md L35 and L38 both endorse this idiom for working-tree fidelity. Promoted modules already expose runnable `__main__` blocks (verified: all 13).

- Implementation complexity: low · Maintainability: high · Performance: same · Alignment: high

### Alternative C — Uniform binstub migration (`["cortex-X", …]` + `uv tool install --reinstall --refresh`)

Replace every subprocess callsite with binstub invocation; require a reinstall step before each test run.

- Implementation complexity: medium · Maintainability: low (env-state coupling, dogfooding friction) · Performance: bad (reinstall cost per `just test`) · Alignment: low (project.md L38 explicitly warns against this for working-tree iteration)

### Alternative D — Eliminate subprocess entirely (direct Python API calls via `monkeypatch.setattr(sys, "argv", …)`)

Fastest, most isolated. Loses fidelity for tests that specifically validate exit-code surface, stderr formatting, or env-var handling under process-boundary conditions — which describes most of the affected files (`_run` helpers in `test_resolve_backlog_item.py`, `test_load_parent_epic.py`, `test_commit_preflight.py`).

- Implementation complexity: high (per-callsite judgment, process-state leakage hazards) · Maintainability: low · Performance: best · Alignment: medium-low

### Alternative E — Scope expansion: add a structural prevention (lint rule / pre-commit hook)

A custom pre-commit hook (~80–150 LOC) that scans `tests/` for `SourceFileLoader('…', 'bin/cortex-*')` and `[sys.executable, str(SCRIPT_PATH), …]` where the path references `bin/cortex-*`. Fits the repo's existing lint-gate aesthetic (`cortex-check-parity`, `cortex-check-path-hardcoding`, `cortex-check-prescriptive-prose`).

- Implementation complexity: medium-high · Maintainability: high (if right-sized) · Performance: n/a · Alignment: medium (exceeds ticket's stated "touch only test files" scope)

### `id(tmp_path)` fix — canonical patterns

1. **`str(tmp_path)` as cache key** — minimum-diff durable fix. Pytest tmp_path strings are unique per test invocation. **Recommended.**
2. `tmp_path.resolve()` (as string) — same uniqueness with symlink normalization. Overkill (pytest tmp_path is already absolute, non-symlinked).
3. Restructure to not cache across test functions — most idiomatic pytest but a bigger rewrite.
4. `WeakValueDictionary` keyed on tmp_path — overengineered.

### Recommended approach

**Alternative B as the default for subprocess sites, plus direct-import rewrites for SourceFileLoader sites, plus `str(tmp_path)` applied to both `test_cortex_log_invocation_parity.py:370` and `test_cortex_complexity_escalator_parity.py:168`. Defer Alternative E.**

Rationale:
- **Uniform `-m` for subprocess** aligns with project.md's explicit working-tree-fidelity idiom (L35, L38). One pattern; one decision rule; no environment-state coupling. Survives venv drift that breaks binstub-based tests.
- **Direct import for SourceFileLoader sites** matches Task 15's canonical model and the pytest-ecosystem consensus that file-based loading is deprecated when the module is importable.
- **Fix both `id(tmp_path)` sites** — the ticket names only one, but the sibling at `test_cortex_complexity_escalator_parity.py:168` carries the same hazard with the same patch shape. Fixing only the named site leaves a known landmine.
- **Defer Alternative E** because (a) the bulk of bin/* promotions are complete, so recurrence risk is shrinking; (b) project.md's Solution horizon test (do I know this needs redoing?) is failed only by a hypothetical future promotion not yet planned; (c) the ticket is medium-criticality and a lint-gate addition exceeds its scope. File as a follow-up backlog item if the same pattern recurs on a future bin/* migration.

## Open Questions

- **Q1 — Sibling `id(tmp_path)` hazard scope expansion (Tradeoffs agent finding):** The same `id(tmp_path)` pattern exists at `tests/test_cortex_complexity_escalator_parity.py:168` and was not named by the ticket. Patch shape is identical to the named site. **Recommend in scope** — fixing only the named site leaves a known sibling hazard. Confirm with user at Spec phase.

- **Q2 — Dashboard test failure mode (Codebase agent finding):** `cortex_command/dashboard/tests/test_feature_cards_pr_url.py` and `cortex_command/dashboard/tests/test_templates.py` contain no `SourceFileLoader` or `bin/cortex-*` subprocess patterns. Their failure mode is likely indirect (transitive ImportError from a sibling collection failure). **Recommend** verifying the failure mode mid-Implement by running `just test` after the eight direct-pattern files are fixed and checking whether these two files still appear in the failure list. If they pass, scope drops from 10 files to 8.

- **Q3 — Structural prevention (clarify-critic finding #4, Applied as Open Question):** Should this ticket carry a lint gate / pre-commit hook to prevent future bin/* promotions from re-introducing the cascade? **Recommend defer** — the bulk of promotable scripts are already promoted, and the Solution horizon principle does not yet justify the structural fix. File a follow-up ticket if the same pattern recurs.

- **Q4 — Bash-wrapper-as-executable exception cases:** Are there any callsites in the 10 affected files whose intent is specifically to exercise the bash wrapper's branch-selection (wheel-import probe vs working-tree fallback) rather than the promoted module? Codebase analysis suggests none — the dedicated `test_cortex_*_parity.py` files already cover wrapper behavior — but call out at Spec if Implement uncovers any.

- **Q5 — Secondary blast radius:** Fixing import-/collection-level failures may unmask test failures previously hidden by `ImportError` at module load. The closeout signal (`just test` exits 0 or down to the pre-existing `test_log_invocation_perf` failure) is the binding contract; if new failures surface, surface them at Implement for triage rather than auto-expanding scope.

## Considerations Addressed

No `research-considerations` were passed; this section is omitted.
