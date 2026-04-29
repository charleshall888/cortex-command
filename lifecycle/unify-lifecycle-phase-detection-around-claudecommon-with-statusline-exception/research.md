# Research: Unify lifecycle phase detection around `cortex_command.common` with statusline exception

## Codebase Analysis

### Current state of `cortex_command/common.py`

- `detect_lifecycle_phase(feature_dir: Path) -> str` at `cortex_command/common.py:88-156`. Returns one of `{"research", "specify", "plan", "implement", "review", "complete", "escalated"}`. **Does NOT emit `implement:N/M` or `implement-rework:cycle`** — those come from the bash callers, not the canonical Python.
- A `detect-phase` CLI subcommand **already exists** at `cortex_command/common.py:453-458` (`_cli_detect_phase`). It currently does `print(detect_lifecycle_phase(Path(args[0])))` — bare phase string, no JSON, no progress info.
- CLI dispatch shim at `cortex_command/common.py:469-492` uses raw `sys.argv` (no argparse). Existing subcommands: `detect-phase`, `normalize-status`.
- The `cortex` console script is declared at `pyproject.toml:19-21` and dispatches via `cortex_command.cli`. Subcommands include `init`, `overnight start|status|cancel|logs`, etc.

### Current state of `hooks/cortex-scan-lifecycle.sh`

- `determine_phase()` at `hooks/cortex-scan-lifecycle.sh:170-207`. Bash ladder; emits `complete`, `research`, `specify`, `plan`, `review`, `escalated`, `implement:checked/total`, `implement-rework:cycle_num`.
- Comment at `hooks/cortex-scan-lifecycle.sh:168` already says: `# Mirrors claude.common.detect_lifecycle_phase — keep in sync if phase model changes`. **The mirror has already drifted** — bash emits richer states (`implement-rework`, progress counts) than canonical Python returns. The "keep in sync" comment did not prevent this.
- Hook iterates over `lifecycle/*/` and calls `determine_phase` per directory at `hooks/cortex-scan-lifecycle.sh:247`. **N invocations per SessionStart**, where N = active feature directories.
- Top-level hook is canonical; mirrored byte-identical to `plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` via `just build-plugin` (`justfile:475-507`); enforced by `.githooks/pre-commit:149-176`.

### Current state of `claude/statusline.sh`

- Bash phase ladder at `claude/statusline.sh:377-402`. Mirror of the hook's logic, including `implement:$_lc_checked/$_lc_total` emit.
- `implement:N/M` parser at `claude/statusline.sh:535-546` splits the format string into a progress bar.
- Comment at `claude/statusline.sh:377` says: `# --- Phase detection (fast, mirrors cortex-scan-lifecycle.sh) ---` — currently in sync with hook (both bash, same logic).

### Current state of `skills/lifecycle/SKILL.md`

- Step 2 "Artifact-Based Phase Detection" at `skills/lifecycle/SKILL.md:43-66` is prose pseudocode read by an LLM, not executed. Post-#097 the override-logic block (`.dispatching` marker + worktree-aware override) has been deleted. Step 2 is now a prose ladder describing the same artifact-presence rules as the canonical Python.

### Python call sites of `detect_lifecycle_phase()` — return-shape consumers

| Path | Line | Consumption | Breaking change risk |
|---|---|---|---|
| `cortex_command/dashboard/data.py` | L322 | `current_phase: str \| None = detect_lifecycle_phase(...)` — assigned to dict key | HIGH |
| `backlog/generate_index.py` | L115 | `lifecycle_phase: str \| None = detect_lifecycle_phase(lc_dir)` — written to `backlog/index.json` | HIGH |
| `cortex_command/common.py` | L458 | CLI handler: `print(detect_lifecycle_phase(...))` | MEDIUM |

### Hidden 5th mirror — `parse_plan_progress`

`cortex_command/dashboard/data.py:340-362` re-implements plan-task counting with a **different regex** than the canonical detector:
- `parse_plan_progress`: `re.findall(r"\[x\]", text, re.IGNORECASE)` — counts every checkbox.
- `detect_lifecycle_phase`: implicitly uses `**Status**: [x]` pattern (see hook L194 / statusline L394).

The "4 implementations" framing in the ticket undercounts: there is also a 5th progress-counting mirror in the dashboard. Even after the proposed change, drift remains between the canonical detector's count semantics and `parse_plan_progress`.

### Serialized phase contract — `backlog/index.json` and frontmatter

- `backlog/index.json` (e.g. L85, L253, L283) stores `"lifecycle_phase": "specify"` etc. as a scalar string.
- Frontmatter writes via `cortex-update-item` set `lifecycle_phase=<string>` (also string).
- The dashboard tests at `cortex_command/dashboard/tests/test_data.py:1150` and templates test at `test_templates.py:156` pin literal phase strings.

A return-shape change from `str` → `dict` either (a) breaks `backlog/index.json` schema, (b) breaks dashboard tests that gate on the literal string, or (c) requires a boundary projection layer the ticket doesn't mention.

### Plugin distribution mechanics

- `hooks/cortex-scan-lifecycle.sh` is shipped via the `cortex-overnight-integration` plugin (`justfile:475-507`).
- The plugin manifest at `plugins/cortex-overnight-integration/.claude-plugin/plugin.json` **does not declare a Python or `cortex` CLI dependency**. A user installing only the overnight plugin (e.g. headless server) gets a hook that subprocesses to a Python module that may not be on PATH.
- Drift hook at `.githooks/pre-commit:149-176` enforces byte-identity between top-level source and plugin mirror.

### Existing `bin/cortex-*` script conventions

- `#!/usr/bin/env python3` shebang.
- Raw `sys.argv` (no argparse for the CLI dispatcher; argparse used inside subcommand handlers).
- Output: minified JSON (or NDJSON) to stdout; errors to stderr.
- Exit codes: 0 (success); 2/3/64/70 for distinct failure classes.
- First import-line invokes `cortex-log-invocation` shim (fail-open telemetry).

### Files that will change (assuming Approach A as written)

| File | Change | Risk |
|---|---|---|
| `cortex_command/common.py` | Extend `detect_lifecycle_phase()` return; teach it `implement-rework`, cycle, checked/total. Update `_cli_detect_phase` to emit JSON. | HIGH (semantic + return-type breaking) |
| `hooks/cortex-scan-lifecycle.sh` | Replace `determine_phase()` body with subprocess + jq + re-emit `implement:N/M`. | MEDIUM (bash glue layer) |
| `plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` | Auto-regenerated via `just build-plugin`. | low |
| `claude/statusline.sh` | Add documenting comment. | low |
| `skills/lifecycle/SKILL.md` | Replace Step 2 prose ladder with reference to the CLI. | MEDIUM (prose, agent-interpreted) |
| `cortex_command/dashboard/data.py` | Adapt `current_phase` assignment to new shape; update tests. | HIGH (dashboard breakage) |
| `backlog/generate_index.py` | Adapt `lifecycle_phase` projection to keep `index.json` a string. | MEDIUM |
| `cortex_command/dashboard/tests/test_data.py` + templates tests | Update literal-string assertions. | MEDIUM |

### Conventions to follow

- Bash shebang `#!/bin/bash` (macOS bash 3.2 compatible); `set -euo pipefail` in scripts that don't already.
- Python CLI: minified JSON to stdout, errors to stderr, exit codes independent of format.
- Plugin distribution: edit canonical sources only; run `just build-plugin` before commit.
- New `bin/cortex-*` scripts are subject to `bin/cortex-check-parity` static gate; `python3 -m cortex_command.X` CLIs are not.

## Web Research

### Python `__main__` module CLI patterns

- Canonical pattern: keep `__main__.py` minimal (parse args, dispatch); real implementation lives in importable modules. `def main(argv=None) -> int` is testable; the guard does `sys.exit(main())`.
- argparse subparsers + `set_defaults(func=callback)` is the textbook pattern. Click/Typer add import-time cost — for low-latency hook targets, plain argparse is preferred.
- `python -X importtime` (or `PYTHONPROFILEIMPORTTIME=1`) is the recommended way to profile cold-start before scoping latency-sensitive work.

### Bash-to-Python subprocess cold-start cost

- `python3 -c "pass"`: typically 15–40 ms on modern x86_64; documented at "8–100 ms" depending on Python version, OS, `.pth` files, venv. Source: pythondev.readthedocs.io, LWN.
- `python3 -m package.module` adds package-import overhead. With typical stdlib (`json`, `pathlib`, `argparse`, `sys`, `os`): expect 30–80 ms total on dev hardware; heavier deps push it higher.
- ARM/slow targets: 200ms+ (Raspberry Pi 3 = ~198ms full Python 3.6 startup).
- Mitigations: lazy imports (PEP 690/810), ensure `__pycache__` writable, profile with `-X importtime`. `-S` flag breaks venv discovery — usually not worth it.

**Implication for this work**: cold-start is acceptable for a single hook invocation but **scales with N feature directories** in a SessionStart loop. Profile before claiming "hook can afford this."

### Inter-process structured-data conventions

- `--format json` + `jq` is the industry standard (`clig.dev`, GitHub CLI, kubectl).
- Stdout for JSON, stderr for everything else. Exit codes independent of output format.
- Minified JSON with trailing newline is the bash-friendly default.
- Anti-pattern: parsing JSON in bash with `sed`/`awk` (success rates collapse on nested data).

### Canonical-implementation + bash-mirror anti-pattern mitigations

Documented patterns when both must coexist:

1. **Drift-detection test (golden fixture)** — most common; CI runs both implementations on a fixture corpus and asserts identical output. The cortex repo's existing `.githooks/pre-commit` drift gate is in this family.
2. **Code generation from a spec** — works for data-driven logic (regex tables, lookup maps); overkill for procedural logic.
3. **Golden-file tests** — canonical produces the golden file; mirror is asserted against it.
4. **Comment markers** — improve human maintenance but **provide no mechanical guarantee**. Real-world precedent: shell completion scripts uniformly use codegen, never hand-written mirrors.

### JSON output conventions (from `clig.dev`, `gh`, `kubectl`)

- Stdout: structured data only.
- Stderr: errors, warnings, progress.
- Exit code 0/non-zero independent of `--json`.
- Errors in `--json` mode: most tools (`gh`) emit plain text to stderr + non-zero exit; some emit `{"error":"..."}` JSON to stdout.
- Trailing newline always.
- Minified is fine for script consumers; pretty-print for humans.

## Requirements & Constraints

### Statusline latency budget (`requirements/observability.md`)

- L23: `Invocation latency < 500ms` — acceptance criterion.
- L91: `Statusline < 500ms per invocation` — non-functional latency constraint.
- L20: "Active lifecycle feature name and phase match `events.log`" — phase model must stay coherent across statusline and event-log writers.

**Implication**: statusline cannot subprocess to Python on the hot path. Bash mirror is structural, not optional.

### Project-level constraints (`requirements/project.md`)

- L19: "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." — drift reduction must be real, not relocation.
- L25: file-based state, no DB, atomic writes.
- L27: `bin/cortex-*` parity gate. Closed enum at `bin/.parity-exceptions.md`. **`python3 -m cortex_command.X` CLIs are NOT subject to this gate** — they are distinct from `bin/cortex-*` scripts.

### Pipeline / hook constraints (`requirements/pipeline.md`)

- File-based state reads have no locks; atomic `os.replace()` makes mid-mutation reads safe.
- No explicit hook latency requirement — hooks tolerate higher latency than statusline.

### Multi-agent (`requirements/multi-agent.md`)

- Overnight orchestrator depends on accurate phase detection for dispatch eligibility (L42, L48).
- File-based reads are thread-safe under forward-only transitions.

### No requirements violated by the proposed approach

The < 500ms statusline budget is the only hard constraint, and the proposed approach honors it by exempting the statusline. No other requirement is in conflict.

## Tradeoffs & Alternatives

Five approaches evaluated. Comparison table follows.

### Approach A — Hook subprocesses to extended-shape CLI (ticket's proposal)

**Description**: Extend `detect_lifecycle_phase()` to return `{phase, checked, total, cycle}`. Update existing CLI (or add a `--json` flag / `detect-phase-detailed` subcommand). Hook subprocesses, parses JSON, re-emits `implement:N/M` for statusline. Skill prose references the CLI. Statusline keeps bash ladder + comment.

**Pros**: 4→3 drift; ~50–70 LOC core change; follows existing thin-wrapper pattern.

**Cons**: 
- Existing `_cli_detect_phase` already emits bare-string output — silently switching to JSON is a breaking change for unknown shell wrappers and agent prompts.
- `cortex_command/dashboard/data.py:322` and `backlog/generate_index.py:115` consume `str | None`; dict return is a breaking change to two files the ticket doesn't list.
- `backlog/index.json` and frontmatter `lifecycle_phase` are serialized as strings — the dict return either breaks the schema or requires a boundary projection layer.
- The 5th mirror (`parse_plan_progress`) is left in place — drift is 5→4, not 4→3 in absolute terms.
- Hook bash glue (subprocess → jq → re-emit `implement:N/M`) is itself a phase-format implementation; net contract surfaces become 5 (Python schema, hook jq parse, hook text re-emit, statusline parse, statusline phase grouping) rather than the claimed 3.
- No mechanical guarantee against statusline drift — same "keep in sync" comment pattern that already failed on the hook.

### Approach B — Migrate hook to Python entirely

**Description**: Rewrite hook as Python module imported in-process. Hook fully Python; statusline still bash. Net drift 4→2.

**Pros**: zero subprocess hop; no JSON glue; cleanest reduction.

**Cons**: 
- Breaks established bash hook convention in this repo.
- Plugin manifest doesn't declare Python dep — users installing only `cortex-overnight-integration` (e.g. headless server) get a broken hook.
- SessionStart hook would need to import `cortex_command.common` per-session; cold-start scales the same way as Approach A.
- More invasive than Approach A; harder to ship incrementally.

### Approach C — Sourced-bash mirror with drift test only

**Description**: Don't unify; add a golden-fixture test that runs all implementations and asserts equivalence.

**Pros**: zero refactor risk; catches drift at commit time.

**Cons**: 300+ LOC of duplication remains; treats symptom, not cause; cognitive burden unchanged.

### Approach D — Generated bash from Python (codegen)

**Description**: Define phase logic once in Python; codegen the bash for hook + statusline; commit both.

**Pros**: single source; statusline still bash (latency preserved); deterministic.

**Cons**: new tooling; debugging friction; merge conflicts; no codegen infra in this repo today.

### Approach E — Narrow CLI (DR-2 strict)

**Description**: CLI returns only `{phase}`; hook re-derives N/M from plan.md independently.

**Pros**: DR-2 compliant.

**Cons**: hook still has its own progress-counting code → drift surface unchanged (4→4 or worse); creates phase/progress asymmetry; defeats the unification goal.

### Comparison

| Dimension | A (proposed) | B (Python hook) | C (drift test) | D (codegen) | E (narrow CLI) |
|---|---|---|---|---|---|
| Implementation complexity | Medium (CLI semantics + breaking dashboard/index.json) | Medium-High (rewrite hook, new dep) | Low (test only) | Medium-High (new infra) | Low-Medium |
| Maintainability | Mixed (3 impl + glue layer + agent prose) | Better (2 impl, but plugin-dep gap) | Worse (4 impl + test) | Best (1 source) | Worse (asymmetric) |
| Performance | Hook OK, scales with N features | Hook OK if pre-imported | Zero overhead | Zero subprocess | Hook OK |
| Pattern alignment | Mostly OK, breaks `bin/index.json` schema | Breaks bash-hook convention | Non-invasive | Breaks "edit-the-file" convention | Breaks unification goal |
| Real drift reduction | 5→4 (parse_plan_progress remains) | 5→3 | 5→5 | 5→2 | 5→5 |
| Mechanical guarantees | Comment only (already failed) | None | Test (strong) | Codegen (strong) | None |

### Recommended approach

**Approach A as a starting point, but with three load-bearing modifications surfaced by the adversarial review** (any of these may be relaxed during spec by user decision):

1. **Reconcile Python's semantics with the hook's BEFORE the CLI work.** Today Python returns `"implement"` for both mid-implement and CHANGES_REQUESTED-rework; the bash hook distinguishes them as `implement` vs `implement-rework:cycle`. Treating "extend return type" as a minor schema change masks a behavior change that immediately breaks `cortex_command/dashboard/data.py:1150` tests and changes what `backlog/index.json` records. Reconciling semantics is the load-bearing work; the CLI is downstream.
2. **Don't extend the existing CLI in place.** Either add a `--json` flag (default keeps bare-string) or a sibling subcommand `detect-phase --detailed`. Preserves backward compatibility for unknown callers.
3. **Add a parity test, not a comment.** A pytest that runs both Python and bash detectors against a fixture matrix and asserts equivalence. The comment-only approach has empirically failed (hook already drifted from `claude.common`).

Approach A's "subprocess fallback to bash" anti-pattern, if any draft suggests it, must be rejected — it re-introduces the very drift being eliminated.

## Adversarial Review

### Failure modes and edge cases

1. **The CLI already exists.** `_cli_detect_phase` at `cortex_command/common.py:453-458` emits the bare phase string today. The ticket frames the CLI as new work; it isn't. Switching its output to JSON-by-default is a breaking change for any shell wrapper, agent prompt, or human caller that today relies on `phase=$(python3 -m cortex_command.common detect-phase $dir)` returning a single line of text.
2. **Python and bash are NOT semantically equivalent today.** Python returns `"implement"` for CHANGES_REQUESTED-rework; bash hook returns `"implement-rework:cycle"`. Python emits no progress; bash emits `implement:N/M`. "Promote Python as canonical" silently changes behavior at every existing Python call site — this is the load-bearing work, not a schema tweak.
3. **Dashboard tests pin literal `"implement"`.** `cortex_command/dashboard/tests/test_data.py:1150` and `test_templates.py:156` gate on the string. Schema change cascades to test files the ticket doesn't list.
4. **`backlog/index.json` is a serialized string contract.** L85, L253, L283 of `backlog/index.json` show `"lifecycle_phase": "specify"`. Switching the function return to dict either breaks the schema or requires a boundary projection at `backlog/generate_index.py:115` — neither is in scope as currently written.
5. **5th mirror missed.** `cortex_command/dashboard/data.py:340-362` (`parse_plan_progress`) implements progress counting with a different regex than `detect_lifecycle_phase`. The "4→3" framing undercounts; real drift is 5, and Approach A reduces it to 4 (or maybe still 5 if the boundary projection is sloppy).
6. **Schema is underspecified.** What's `cycle` when `phase=complete`? What's `checked/total` when `phase=research`? Null? Zero? Consumers will branch on it.
7. **SessionStart loops over N feature directories.** Cold-start cost is per-invocation; total is N × cold-start. For projects with many active feature directories, the hook's "acceptable" latency budget can blow up.
8. **Plugin runtime dependency not declared.** `plugins/cortex-overnight-integration/.claude-plugin/plugin.json` declares no Python or `cortex` CLI dep. Headless overnight installs may get a broken hook.
9. **Bash glue layer relocates drift.** Subprocess to Python → jq parse → text re-emit → statusline parse. Three serialization layers where one existed; each can mistranslate. Net contract surfaces increase, not decrease.
10. **Statusline "documenting comment" has no mechanical guarantee.** The hook already has the comment "Mirrors claude.common.detect_lifecycle_phase — keep in sync"; the hook has empirically drifted anyway. Same pattern proposed for statusline; same outcome expected.
11. **Skill is read by an LLM, not executed.** Telling the agent to "run `python3 -m cortex_command.common detect-phase`" doesn't reduce drift unless the agent invokes the CLI rather than re-deriving from artifact presence. There is no parity check between skill prose and CLI output.

### Security / anti-patterns

- **Subprocess fallback to bash if Python fails** would re-introduce the very drift the unification eliminates. Must be rejected; if Python is unavailable, the hook should fail visibly.
- **`python3 -m` invocation assumes `python3` resolves to the venv with `cortex_command` installed.** Hook runs from arbitrary `PATH`; multi-Python systems can pick the wrong interpreter. Better: invoke via `cortex` console script (declared at `pyproject.toml:19-21`) which is on PATH after `uv tool install`.
- **JSON-on-stdout from subprocess is brittle when child stderr or warnings leak to stdout.** If `cortex_command.common` ever does `print(...)` at module-import (e.g., a deprecation warning), `jq` chokes. Hook needs disciplined stderr separation.

### Assumptions that may not hold

- A1: existing CLI emits bare phase string and nobody depends on that format. Untested.
- A2: Python and bash detectors are equivalent. **False.**
- A3: < 500ms is the only reason statusline must stay bash. Cold-start in non-Python environments (e.g. login shell with no venv) is also a structural reason.
- A4: `cortex` CLI is available in plugin runtime. Not declared, not enforced.
- A5: drift count is 4. With `parse_plan_progress`, real count is 5.

### Recommended mitigations

1. **Reconcile Python semantics with the hook FIRST.** Add `implement-rework`, `cycle`, `checked`, `total` to `detect_lifecycle_phase` as a separate, tested, behavior-preserving change. Land this before the CLI work.
2. **Don't break the existing CLI's default output.** Add `detect-phase --json` flag (default = bare string), or sibling `detect-phase-detailed` subcommand. Preserve backward compatibility.
3. **Audit `backlog/index.json` consumers and project the dict to a string at the boundary.** Don't change the serialized schema unless that's an explicit, scoped sub-ticket with version bump.
4. **Hook should invoke `cortex detect-phase`, not `python3 -m cortex_command.common`.** The console-script entry is on PATH after install; falls back to a clean failure if cortex isn't installed.
5. **Declare the dependency.** Add a setup-check at top of `cortex-scan-lifecycle.sh` that fails fast with a clear message if `cortex` isn't on PATH. **No bash fallback ladder.**
6. **Add a parity pytest, not a comment.** Run both Python and bash detectors over a fixture matrix; assert equivalence. Apply to hook and statusline. Comments are decorative; tests are the contract.
7. **Account for `parse_plan_progress`.** Either fold into canonical (real 5→3 reduction) or explicitly mark as a 5th mirror with a docstring noting it duplicates the canonical detector.
8. **Profile cold-start before committing to the latency claim.** Measure `python3 -m cortex_command.common detect-phase` × N feature dirs on the slowest target environment. If N×cost approaches 200ms, the hook is paying the same budget the statusline was exempted from.

## Open Questions

1. **Output format & backward compat — for the existing `_cli_detect_phase` CLI**: in-place breaking upgrade to JSON, or `--json` flag (default = bare string), or new `detect-phase-detailed` sibling subcommand? The choice shapes whether unknown shell-wrapper callers break.

2. **Semantic reconciliation as a separate change**: Should the work split into two commits/tickets — (a) bring `detect_lifecycle_phase` to behavioral parity with the hook (add `implement-rework`, cycle, checked, total) and migrate dashboard + backlog-index + index.json schema; (b) only then cut the CLI over and have the hook subprocess to it? Or do it as one bundle?

3. **Hook invocation surface**: `cortex detect-phase` (console script — needs `cortex_command.cli` integration and pyproject `[project.scripts]` entry) vs `python3 -m cortex_command.common detect-phase` (current pattern, but vulnerable to `python3` resolution). Which?

4. **`backlog/index.json` and frontmatter `lifecycle_phase`**: stay as scalar string (project the dict at boundaries) or migrate to structured? If migrate, all consumers (dashboard templates, frontmatter readers, index.json consumers) need updating — likely a separate ticket.

5. **5th mirror `parse_plan_progress`**: fold into canonical now (real 5→3 reduction) or explicitly leave as a 5th mirror with a docstring? The ticket frames the work as "4→3"; if `parse_plan_progress` is in scope the framing is wrong.

6. **Plugin dependency declaration**: How should `cortex-overnight-integration` declare its Python/`cortex` dependency? Manifest field? Setup check at hook entry? Documentation only? Without resolution, headless overnight installs silently get a broken hook.

7. **Parity test scope**: Should the parity test cover Python vs hook, Python vs statusline, hook vs statusline (transitively), or a smaller subset? Fixture matrix design is non-trivial — what's the minimum coverage that catches realistic drift?

8. **Skill prose update strategy**: Replacing the prose ladder with "run the CLI" only unifies if the agent actually invokes the tool. Should the skill be more prescriptive ("MUST invoke; do not re-derive")? Or is agent judgment acceptable here, knowing drift between skill prose and canonical detector remains possible?

9. **Statusline drift mechanical guarantee**: Comment-only (proposed) has empirically failed once. Add a parity test? Add a pre-commit check that diffs the bash phase ladder block against a generated-from-Python reference? Accept the comment + parity test combination as sufficient?

These questions need user decisions before the spec interview can converge on a plan-ready design. They are flagged as the Research Exit Gate for the calling refine skill to resolve in the spec phase.
