# Research: Add path-hardcoding parity gate to prevent cortex/ root drift

> Lifecycle: `add-path-hardcoding-parity-gate-to-prevent-cortex-root-drift`
> Backlog: `203-add-path-hardcoding-parity-gate-to-prevent-cortex-root-drift`
> Parent epic: #200 (consolidate-cortex-artifacts-under-cortex-root)
> Author: refine (inline; parallel-sessions feedback in effect)
> Date: 2026-05-12

## Clarified Intent

Add a new pre-commit parity check, `bin/cortex-check-path-hardcoding`, that scans Python sources (`cortex_command/`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*`) for string literals whose leading path segment is one of the four pre-#202 prefixes (`lifecycle`, `backlog`, `research`, `requirements`) **not** preceded by `cortex/`, with an allowlist file (`bin/.path-hardcoding-allowlist.md`) for legitimate exceptions. The gate prevents silent regression to the pre-relocation layout in any new code, mirroring the existing `bin/cortex-check-parity` and `bin/cortex-check-events-registry` precedents.

## Codebase Analysis

### Existing parity-gate precedents

Three pre-commit gates set the pattern this feature extends:

- **`bin/cortex-check-parity`** (1462 LOC) — SKILL.md ↔ bin/cortex-* parity. Fails open on missing `bin/.parity-exceptions.md`. Two-mode: `--staged` (pre-commit) + ad-hoc filename args. Wired at `.githooks/pre-commit` Phase 1.5, trigger pattern: `skills/*|bin/cortex-*|justfile|bin/.parity-exceptions.md|CLAUDE.md|cortex/requirements/*|tests/*|hooks/cortex-*|claude/hooks/cortex-*`.
- **`bin/cortex-check-events-registry`** (613 LOC) — event-name registry static gate. Fails **closed** on missing `bin/.events-registry.md` (allowlist absence = incomplete authoring). Two-mode: `--staged` + `--audit`. Wired at `.githooks/pre-commit` Phase 1.8 via `just check-events-registry`. The `--root <path>` flag is a test-fixture override.
- **`bin/cortex-check-prescriptive-prose`** (407 LOC) — skill/backlog prose discipline. `--staged` only; wired at Phase 1.85.

The `bin/.parity-exceptions.md` schema (5 columns: `script | category | rationale | lifecycle_id | added_date`, closed-enum category, ≥30-char rationale with forbidden-literal block) is the direct precedent for #203's allowlist.

### Pre-commit wiring (`.githooks/pre-commit`)

The hook is structured as numbered phases (1, 1.5, 1.6, 1.7, 1.8, 1.85, 2, 3, 4). Each gate-extension follows the pattern:

```bash
# Phase 1.<N> — <gate name>
<gate>_triggered=0
while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
        <trigger-pattern>) <gate>_triggered=1; break ;;
    esac
done < <(git diff --cached --name-only --diff-filter=ACMR)

if [ "${<gate>_triggered}" -eq 1 ]; then
    if ! just check-<gate>; then exit 1; fi
fi
```

For #203, **Phase 1.9** slots between prescriptive-prose (1.85) and short-circuit decision (2). Trigger pattern: `cortex_command/**/*.py|bin/cortex-*|hooks/cortex-*|claude/hooks/cortex-*|bin/.path-hardcoding-allowlist.md`. `tests/` is intentionally excluded (test sources legitimately embed violation strings as fixtures; allowlisting test fixtures would balloon).

### Justfile recipes

Existing pattern (justfile:343-361):

```just
check-parity *args:
    python3 bin/cortex-check-parity {{args}}

check-events-registry:
    bin/cortex-check-events-registry --staged

check-events-registry-audit:
    bin/cortex-check-events-registry --audit
```

#203 adds:

```just
check-path-hardcoding *args:
    bin/cortex-check-path-hardcoding --staged {{args}}

check-path-hardcoding-audit:
    bin/cortex-check-path-hardcoding --audit
```

### Empirical scan of current sources

Running the proposed scan retroactively against the post-#202 tree produces these populations (validates the design and grounds the initial allowlist):

#### True positives (drift to fix in this PR)

- **`cortex_command/overnight/daytime_pipeline.py` lines 220, 223, 224, 225, 226, 243, 391** — pattern `cwd / "cortex" / f"lifecycle/{feature}/..."`. The path resolves correctly today because `"cortex"` is prepended by the surrounding join, but the literal `f"lifecycle/{feature}/..."` is a copy-paste vector: anyone copying the line without the `cwd / "cortex" /` prefix produces a pre-#202 path. **Refactor** in this PR to `cwd / Path("cortex/lifecycle") / feature / "plan.md"` style so each literal is self-contained.
- **`bin/cortex-check-prescriptive-prose:43`** — scan glob `"backlog/*.md"`. Stale leftover from pre-#202; should be `"cortex/backlog/*.md"`. **Fix** in this PR (the prescriptive-prose check is itself broken against the post-#202 layout). This is a #202 straggler that #203's empirical scan surfaces.

#### Legitimate exceptions (initial allowlist entries)

- **`bin/cortex-archive-rewrite-paths:65-69`** — `Path("lifecycle") / "archive"`, `Path("lifecycle") / "sessions"`, `Path("research") / "archive"`. This script's job is rewriting archived pre-relocation paths *forward* to the new layout; the bare prefix is the FROM side of the rewrite, not a path the script constructs in new code. Allowlist with category `archive-rewriter`.
- **`bin/cortex-archive-rewrite-paths:203`** — `"lifecycle/sessions/, retros/). Emits one JSON line per slug."` — narrative help/docstring describing what the script rewrites. Allowlist with category `docstring-narrative`.
- **`cortex_command/init/tests/test_relocation_migration.py`** — test fixtures asserting that pre-relocation strings get rewritten. Already out of scan scope (tests/ excluded; this file is under `cortex_command/init/tests/`, so the scan exclusion needs to cover both `tests/` and `**/tests/`).

Pattern-detection regex (final form):

```
# Violation 1: bare prefix as leading path segment (slash form)
["'\']\s*(lifecycle|backlog|research|requirements)/

# Violation 2: bare prefix as full literal (Path()/os.path.join arg form)
\b(Path|os\.path\.join)\(\s*["'\']\s*(lifecycle|backlog|research|requirements)\s*["'\']
```

The slash form is the high-signal pattern (catches f-strings, plain strings, Path("x/y") calls). The full-literal form catches `Path("lifecycle") / "archive"` style. Combined, they cover every realistic regression vector without scanning bare prose.

### Canonical anchor pattern (positive precedent)

Post-#202 sources widely use `Path("cortex/lifecycle")` / `Path("cortex/backlog")` as the canonical anchor — already established in:

- `cortex_command/common.py:435, 449, 508, 520` — `lifecycle_base: Path = Path("cortex/lifecycle")` (function-default; resolver helper)
- `cortex_command/overnight/orchestrator.py:98-107` — `_resolve_user_project_root() / "cortex/lifecycle" / ...`
- `cortex_command/overnight/cli_handler.py` (8 occurrences) — `repo_path / "cortex/lifecycle" / "sessions"`
- `cortex_command/overnight/backlog.py:248` — `DEFAULT_BACKLOG_DIR = Path("cortex/backlog")`
- `cortex_command/overnight/daytime_result_reader.py:69, 130` — `_DEFAULT_LIFECYCLE_ROOT = Path("cortex/lifecycle")`
- `cortex_command/overnight/report.py:52, 125, 616, 631, 709` — `Path("cortex/lifecycle")`, `Path("cortex/backlog")`
- `cortex_command/pipeline/review_dispatch.py:129` — `lifecycle_base: Path = Path("cortex/lifecycle")`

The gate's negative pattern (bare prefix) is precisely the inverse of this established positive pattern.

### Sandbox preflight gate (cross-reference)

Project.md notes that `bin/cortex-check-parity` extends to validate `cortex/lifecycle/{feature}/preflight.md` on sandbox-source diffs. #203's gate is orthogonal — it scans source-code path-literals, not preflight YAML — so no overlap or coupling with that extension.

## Design Decisions

### DR-1 — Pattern: regex on string literals, not AST

**Decision**: Use regex source-text scan, mirroring `cortex-check-parity`'s approach.

**Rationale**: An AST-based scan (e.g., `ast.parse` walking `Constant` nodes) would be more precise, but the regex form is good enough for the realistic regression vectors (slash-prefix literal in any string context), keeps the gate stdlib-only and ~300 LOC, and matches the prevailing style of sibling gates. False positives are handled by the allowlist; false negatives in exotic constructions (e.g., dynamic string assembly via `.format()` with the prefix coming from a variable) are not worth the AST cost — those are not realistic regression vectors.

### DR-2 — Fail-open on missing allowlist

**Decision**: Fail-open. Missing `bin/.path-hardcoding-allowlist.md` = no allowlisted exceptions = strict gate.

**Rationale**: Matches `bin/.parity-exceptions.md` precedent. The allowlist is opt-in for exceptions, not a registry of expected entries — its absence is not "incomplete authoring" (contrast `bin/.events-registry.md`, which fails-closed because every emitted event must be registered). A fresh repo or a repo with no legitimate exceptions is a valid state.

### DR-3 — Scope: include `bin/`, `hooks/`, `claude/hooks/`; exclude `tests/`

**Decision**: Scan `cortex_command/**/*.py`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*`. Exclude `tests/` and any `**/tests/` subtree.

**Rationale**: Tests legitimately embed violation strings as fixtures (e.g., `cortex_command/init/tests/test_relocation_migration.py` tests the relocation rewriter against pre-#202 strings). The cost of allowlisting test fixtures outweighs the value: tests are not a production drift vector — code that runs in overnight or CLI sessions lives in the production trees. `bin/`, `hooks/`, `claude/hooks/` are in scope because they ARE production execution surfaces.

### DR-4 — Two-mode pattern

**Decision**: Support `--staged` (pre-commit, scans staged diff hunks) and `--audit` (full-repo scan, off critical path via `just check-path-hardcoding-audit`). `--root <path>` test-fixture override mirrors `cortex-check-events-registry`.

**Rationale**: Directly applies project.md's two-mode gate pattern. The audit mode is for periodic full-repo sweeps and morning-review checks; pre-commit only scans what's staged.

### DR-5 — Refactor `daytime_pipeline.py` drift in same PR; do not allowlist

**Decision**: The `cwd / "cortex" / f"lifecycle/{feature}/..."` constructions in `cortex_command/overnight/daytime_pipeline.py` are refactored to use `Path("cortex/lifecycle") / feature / "plan.md"` style — not allowlisted.

**Rationale**: These are exactly the drift the gate is designed to prevent. Allowlisting them on first introduction defeats the gate's purpose. The refactor is mechanical (~7 lines, single file) and the resulting code is strictly clearer. The PR therefore lands the gate AND the cleanup it motivates.

### DR-6 — Fix `bin/cortex-check-prescriptive-prose:43` in same PR

**Decision**: The stale `"backlog/*.md"` glob is fixed to `"cortex/backlog/*.md"` in this PR.

**Rationale**: It's a true #202 straggler that the empirical scan surfaces; leaving it broken means the prescriptive-prose check has been silently scanning the wrong (now-empty) directory since the #202 relocation. Tightly coupled to #203's scope — empirical-grounding finding.

### DR-7 — Allowlist schema: mirror `bin/.parity-exceptions.md`

**Decision**: 6-column markdown table: `file | line_pattern | category | rationale | lifecycle_id | added_date`. Closed-enum category. ≥30-char rationale with forbidden-literal block (`internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary`).

Initial categories (closed enum):
- `archive-rewriter` — operates on pre-relocation archived data
- `docstring-narrative` — bare prefix appears in narrative prose (docstring/help/comments)
- `migration-script` — one-shot migration tooling that references the old layout intentionally

**Rationale**: Direct schema parallel to `bin/.parity-exceptions.md` keeps the allowlist authoring discipline consistent across gates. `line_pattern` (a regex or exact-line substring) lets one allowlist row cover multiple occurrences in a single file when they're structurally identical (e.g., the three `Path("lifecycle")` / `Path("research")` calls in `cortex-archive-rewrite-paths`).

### DR-8 — Test file location: `tests/test_check_path_hardcoding.py`

**Decision**: Tests live at `tests/test_check_path_hardcoding.py`, matching the flat convention used by `tests/test_check_parity.py`, `tests/test_check_events_registry.py`, `tests/test_check_prescriptive_prose.py`.

**Rationale**: Convention. Keeps test discovery consistent and groups gate tests together.

## Implementation Touchpoints

- **NEW**: `bin/cortex-check-path-hardcoding` (~300–400 LOC, stdlib-only Python, executable)
- **NEW**: `bin/.path-hardcoding-allowlist.md` (initial allowlist with `archive-rewriter` + `docstring-narrative` entries)
- **NEW**: `tests/test_check_path_hardcoding.py` (unit + integration tests)
- **MODIFY**: `.githooks/pre-commit` — add Phase 1.9 (trigger pattern + invocation)
- **MODIFY**: `justfile` — add `check-path-hardcoding` and `check-path-hardcoding-audit` recipes (near line 343–361)
- **MODIFY (drift cleanup)**: `cortex_command/overnight/daytime_pipeline.py` — refactor lines 220–391 to canonical-anchor style (~7 lines)
- **MODIFY (#202 straggler fix)**: `bin/cortex-check-prescriptive-prose:43` — `"backlog/*.md"` → `"cortex/backlog/*.md"`
- **MODIFY (parity wiring extension)**: `bin/cortex-check-parity` — may need to recognize `bin/cortex-check-path-hardcoding` as having an in-scope reference (justfile recipe + .githooks/pre-commit). The existing wiring-detection logic likely covers this automatically since both are referenced from `justfile` and `.githooks/pre-commit`; verify in spec phase.

## Open Questions

All resolved or deferred to spec — no blocking unknowns for plan/implement:

- **Q1**: Should the `cortex_command/init/tests/test_relocation_migration.py` test fixtures fall under `tests/` exclusion or `**/tests/` exclusion? — **Resolved**: scope exclusion is `**/tests/**` (any tests subtree under any source root), so this file is excluded. The scan-root logic excludes `tests/` directories anywhere.
- **Q2**: Does the `archive-rewriter` category fit only `cortex-archive-rewrite-paths`, or should it generalize? — **Deferred to spec**: confirmed during spec interview alongside the final closed-enum category list.
- **Q3**: Should the gate also flag `.md` files (e.g., skill prose, docstrings) for the bare-prefix patterns? — **Deferred: No for v1.** The prescriptive-prose gate already covers skill prose discipline. Markdown bare-prefix mentions in docs are narrative, not code-path drift, and would balloon the allowlist with no real protection gain. If markdown drift becomes a problem, add as a separate `--include-markdown` mode in a follow-up ticket — do not expand v1 scope.
