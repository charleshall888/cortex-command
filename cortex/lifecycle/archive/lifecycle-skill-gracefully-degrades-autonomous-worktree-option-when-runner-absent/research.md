# Research: Lifecycle skill gracefully degrades autonomous-worktree option when runner absent

Ticket: `123-lifecycle-autonomous-worktree-graceful-degrade.md`
Lifecycle slug: `lifecycle-skill-gracefully-degrades-autonomous-worktree-option-when-runner-absent`
Tier: complex · Criticality: high

## Epic Reference

This ticket descends from epic 113 (cortex-command distribution split). See `research/overnight-layer-distribution/research.md` — DR-2 establishes that the `lifecycle` skill ships in the `cortex-interactive` plugin so users get the interactive workflow without the runner CLI; the runtime-probe behavior specified in this ticket is the load-bearing mechanism that makes that split safe.

## Codebase Analysis

### Files that will change

- `skills/lifecycle/references/implement.md` (source of truth)
- `plugins/cortex-interactive/skills/lifecycle/references/implement.md` (plugin copy, regenerated from source by `just build-plugin` and drift-enforced by the pre-commit hook)

No new files are created. Both copies must end up identical in any commit; the drift-enforcement pre-commit hook (rewritten in commit `79390c7`) regenerates the plugin tree from source and refuses commits that diverge.

### Authoritative module name

- `cortex_command.overnight.daytime_pipeline` exists at `cortex_command/overnight/daytime_pipeline.py` and is the only valid form.
- `claude.overnight.daytime_pipeline` (used in the ticket body's "Scope" section, line 28) **does not exist anywhere in the repo**. It is a stale-name typo; the spec must use `cortex_command.overnight.daytime_pipeline`.
- Cross-checked against `skills/lifecycle/references/implement.md:14` and `:71` — both reference `cortex_command.overnight.daytime_pipeline`.

### Closest prior art for conditional menu manipulation

`skills/lifecycle/references/implement.md:17` — the **uncommitted-changes guard**:

> Immediately before the `AskUserQuestion` call, run `git status --porcelain` (no path filter, no additional flags). If non-empty output is returned, the option that keeps the user on the current branch is demoted in place: (a) prepend the fixed warning … as a one-line prefix to that option's description, and (b) strip the `(recommended)` suffix from that option's label if present. The option remains selectable and stays at its existing position — no removal, no gating pre-question. If `git status --porcelain` exits non-zero (e.g., missing `.git`, corrupt index, bisect/rebase state), **the guard does not fire** — neither the demotion nor the warning prefix are applied — a single-line diagnostic `uncommitted-changes guard skipped: git status failed` is surfaced alongside the prompt, and the pre-flight continues normally as a fallback.

Pattern elements to reuse: (1) single Bash call before `AskUserQuestion`, (2) check exit code + output, (3) conditionally mutate the options list, (4) explicit **fail-open fallback** with diagnostic line on guard error. The runtime probe here goes one step further than the existing guard — instead of demoting in place, it **removes** the autonomous-worktree option from the options array. That option-removal pattern has no precedent in the codebase (everything else demotes-in-place), so this ticket establishes it.

### Integration points

- The `cortex` CLI ships via `pyproject.toml [project.scripts]` (`cortex_command.cli:main`); plugins cannot ship console scripts. So `cortex` on PATH is owned by the CLI tier (`uv tool install`), not by either plugin.
- `cortex_command/overnight/daytime_pipeline.py` imports `cortex_command.overnight.{auth, batch_runner, deferral, feature_executor, orchestrator, outcome_router, state, types}` and `cortex_command.pipeline.worktree` at top level — full module load is non-trivial.
- `cortex_command/overnight/__init__.py` re-exports submodules at import time (a star-import-style chain) — even a minimal "is parent package present" probe pays for the parent's `__init__` to run.
- The overnight runner's worker dispatch does **not** invoke the lifecycle skill (worker `_ALLOWED_TOOLS` excludes Agent/Task), so the probe affects the interactive Claude Code context only. No probe runs inside dispatched worker subprocesses.

### Conventions to follow

- Bash guard pattern (single call, no compound, exit-code branching) per the uncommitted-changes guard.
- Fail-open fallback with a one-line diagnostic when the guard itself errors.
- Mutate the options list before the `AskUserQuestion` call; do not split into a pre-question conditional or re-render after selection.
- Documentation lives inline in the reference file (no separate doc).

## Web Research

### Probe-mechanism options (Python idioms)

- `importlib.util.find_spec("module")` — canonical Python optional-dep probe. Cheaper than `import` because no top-level execution of the target module. **Caveat**: For dotted names, `find_spec` imports parent packages — so `find_spec("cortex_command.overnight.daytime_pipeline")` runs `cortex_command/__init__.py` and `cortex_command/overnight/__init__.py`. The latter has the star-import chain noted above.
- `try: import X` — catches `ModuleNotFoundError` (subclass of `ImportError`). Slightly more expensive than `find_spec` because it also runs the target module's top-level code.
- `shutil.which("cortex")` — PATH lookup only; doesn't validate that the binary works or that the corresponding Python module is importable.
- `subprocess.run(["cortex", "--version"])` — fully validates a binary, but adds prompt-injection surface (the binary's stdout becomes data the agent reads). Not appropriate in agent contexts when a Python probe suffices.

### Adversarial reframe (this matters)

In a markdown skill, the probe is **not in-process Python** — the model reads the markdown and dispatches a `Bash` tool call. So `python3 -c "import importlib.util; ..."` is itself a subprocess. The "find_spec sidesteps subprocess" guidance from web research applies only when the calling context is in-process Python. Here, every probe is a fresh `python3` invocation. The choice between `find_spec` and `import` reduces to: which costs less inside that subprocess?

Measured (per Adversarial agent, working dir of this repo):
- `python3 -c "import cortex_command.overnight.daytime_pipeline"` → ~476ms
- `python3 -c "import importlib.util; importlib.util.find_spec('cortex_command.overnight.daytime_pipeline')"` → ~117ms
- `python3 -c "import importlib.util; importlib.util.find_spec('cortex_command.overnight')"` → ~110ms (parent only)
- `python3 -c "import importlib.util; importlib.util.find_spec('cortex_command')"` → ~80ms (top-level only)

The dominant cost is Python startup + parent-`__init__` execution; the target submodule resolution is cheap. Probing the **top-level package** (`cortex_command`) is sufficient: if that's importable, then so is `cortex_command.overnight.daytime_pipeline` (they ship together — a partial install is not a supported state).

### Plugin-ecosystem prior art

- Claude Code does **not** support first-class plugin-dependency manifests or skill overlays. Issues `anthropics/claude-code#27113` and `#9444` are closed/stale. So static-hide alternatives that depend on plugin-system overlays are not available — runtime probe is the supported option.
- Industry CLI convention (`gh`, `git`, `kubectl`) is silent-hide for missing optional features; explicit upgrade hints appear only on direct invocation by name. Aligns with the ticket's "no nag" requirement.

### Documentation references

- `importlib.util.find_spec` — https://docs.python.org/3/library/importlib.html#importlib.util.find_spec
- `shutil.which` — https://docs.python.org/3/library/shutil.html#shutil.which
- Claude Code skills — https://code.claude.com/docs/en/skills

## Requirements & Constraints

### Load-bearing requirements

- `research/overnight-layer-distribution/research.md` (DR-2, lines 248–250): `cortex-interactive` is a self-contained plugin housing all non-runner skills including `lifecycle`; the autonomous-worktree mode "gracefully degrades when the runner CLI isn't installed (hides the menu item); other lifecycle modes still work."
- Same document, Risks Acknowledged: "Autonomous-worktree graceful degrade is a new runtime behavior the lifecycle skill must learn. When `cortex` is not on PATH or `cortex_command.overnight.daytime_pipeline` is not importable, the 'Implement in autonomous worktree' menu option must be **hidden (not errored)**."
- `requirements/project.md:30` ("Graceful partial failure"): explicitly about overnight task-level failure recovery, **not menu UX**. So this attribute does not constrain silent-vs-observable for the menu degrade — it neither requires nor forbids observability of the hidden option.
- `requirements/project.md:19` ("Complexity must earn its place"): the runtime probe must be the simplest mechanism that solves the real ModuleNotFoundError; gold-plating (telemetry, hints, re-probing) is out.

### Architectural constraints

- The lifecycle skill is shared infrastructure — changes are operationally sensitive but not technically gated. No requirement forbids subprocess invocation from skills (the existing uncommitted-changes guard already runs `git status --porcelain`).
- Atomic file writes are the norm for persistent state but irrelevant here (this is a read-only menu render decision, no state to write).
- Both `skills/` and `plugins/cortex-interactive/skills/` copies must be updated in the same commit; the pre-commit drift hook will reject divergence.

### Scope boundaries

- In: lifecycle skill's Implement-phase menu only.
- Out: sibling skills (`critical-review`, `morning-review`) — owned by ticket 120's codebase-import-graph audit. Ticket 120 does not define a probe pattern; ticket 123 establishes one that 120 may adopt later.
- Out: re-probing mid-session if the user installs/uninstalls the runner during a session (edge case noted, not handled).

## Tradeoffs & Alternatives

### Alternative A — Static hide via plugin-layered skill definitions

`cortex-interactive` ships a 2-option `implement.md`; `cortex-overnight-integration` overlays a 3-option version when also installed. **Fatal flaw: infeasible.** Claude Code's plugin system is strictly additive (each plugin's `skills/` directory loads in full); there is no documented mechanism for skill overlays, conditional loading, or per-plugin manifests with exclusion rules. Implementing this would require building plugin composition infrastructure — far outside this ticket's scope. Rejected.

### Alternative B — Error-trap at dispatch site

Keep the menu as 3 options. If user picks "Implement in autonomous worktree" and §1a's subprocess launch fails with `ModuleNotFoundError`, catch it and show a friendly "install cortex-overnight-integration" message with retry/skip/abort prompts.

- Pros: localized change, no menu probing overhead, reuses the §2 Failure Handling retry/skip/abort pattern.
- Cons: failure surfaces **after** user selection — wasted attention; opposite of the ticket's "silent hide" requirement; leaves a 3-option menu that includes a broken option.
- Rejected for failing the ticket's UX requirement.

### Alternative C — Env-var feature flag

`cortex-overnight-integration` installer sets `CORTEX_OVERNIGHT_AVAILABLE=1`; skill checks this var.

- Pros: cheapest probe (~1µs env read).
- Cons: correctness depends on installer hygiene; stale on uninstall (env var remains set, option appears, then crashes); cross-shell config drift; recursive-worktree env-inheritance brittleness.
- Closest existing precedent: `LIFECYCLE_SESSION_ID` and `CORTEX_COMMAND_ROOT` are env vars set by the harness, but those are session-correlation/state-location vars, not optional-feature flags. No env-var-as-feature-flag pattern exists in this codebase today.
- Rejected as primary; note as fallback if probe cost becomes measurably problematic in real use.

### Baseline (recommended) — Runtime probe + silent hide

Single Bash call before `AskUserQuestion` in §1 Pre-Flight Check; if probe fails, remove the autonomous-worktree option from the options array passed to `AskUserQuestion`. Documented in implement.md.

- Implementation complexity: low — ~10–15 lines added to one place (mirrored to two files via build-plugin).
- Maintainability: good — self-contained; if module path changes, one line updates.
- Performance: ~80–110ms per implement-phase invocation if probing the top-level package via `find_spec`. ~476ms if probing the full daytime_pipeline import (avoid this).
- Alignment: matches the uncommitted-changes guard pattern almost exactly (Bash call before menu, exit-code branching, fail-open fallback).
- **Recommended.**

### Cross-cutting decisions

- **Probe placement**: just-in-time in `references/implement.md` §1 Pre-Flight Check (not hoisted to `SKILL.md`). The probe is feature-specific to the implement phase; hoisting would tax research/specify/plan/review invocations for no benefit.
- **Probe target**: top-level package `cortex_command` (not the full `cortex_command.overnight.daytime_pipeline`). Cheaper (~80ms vs ~476ms) and equivalent — partial installs aren't a supported state; if `cortex_command` imports, the daytime_pipeline submodule is available.
- **Probe form**: `python3 -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('cortex_command') else 1)"`. Exit-code branching, no stdout parsing, no prompt-injection surface.
- **Drop the `cortex --version` PATH check** (open-question Q1 below): redundant. The §1a Daytime Dispatch path invokes `python3 -m cortex_command.overnight.daytime_pipeline` — it never shells out to the `cortex` binary. The PATH check would add a second subprocess, double the cost, and introduce a false-positive failure mode (PATH-shadowed `cortex` reports a version while `python3` lacks the package). One probe (the import) is the right answer.
- **Fail-open semantics**: if the probe subprocess errors (e.g., `python3` itself missing, weird shell), the guard does not fire — show all three options and surface a one-line diagnostic. Same precedent as the uncommitted-changes guard. This is the safer, more discoverable behavior than fail-closed.

## Adversarial Review

The adversarial agent surfaced several concrete issues that shape the spec.

### Confirmed issues addressed by the spec

1. **The probe is a model-dispatched Bash call, not in-process Python.** The "find_spec sidesteps subprocess" framing from web research applies only to in-process Python. Every probe here is a fresh `python3 -c` invocation. This refines the probe-cost analysis above and is the basis for choosing top-level-package probing.
2. **Probing the full daytime_pipeline module is wasteful** (~476ms vs ~80ms for `cortex_command` top-level). The `cortex_command/overnight/__init__.py` star-import chain is responsible for most of the overhead. Probe the top-level package.
3. **The `cortex --version` PATH check is redundant.** §1a Daytime Dispatch never invokes the `cortex` binary; it runs `python3 -m`. Drop the PATH check.
4. **Probe error fallback must be specified.** Fail-open (show all options + diagnostic) is the right precedent — matches the uncommitted-changes guard. The ticket body did not specify this; the spec must.
5. **Drift atomicity**: source + plugin copy must be staged in the same commit. The build-plugin recipe regenerates the plugin tree, so as long as the source change is staged and `just build-plugin` is run before commit, the pre-commit hook's drift check passes. The spec must mention this explicitly.

### Issues acknowledged but accepted

6. **Resume-session re-probe**: a user resumes a lifecycle in implement phase after uninstalling the runner; the option silently vanishes on resume. Accepted as designed — fixing it would require persisting the probe result across sessions, which violates the simplicity bar. The ticket's out-of-scope clause on re-probing implicitly accepts this surprise.
7. **Python-interpreter shadowing**: user has `python3` resolving to a system Python that lacks `cortex_command`, while `cortex` actually works through `uv`'s isolated venv. This is a legitimate false-negative. Mitigation: documenting the fail-open path + diagnostic gives the user a discoverable signal; full mitigation would require detecting the uv-tool Python explicitly, which is out of scope.
8. **Test surface for skill runtime behavior is absent.** No prior art for testing a markdown skill's conditional behavior. The pre-commit drift hook covers source/plugin parity but not runtime correctness. The spec will note that the test approach is manual (toggle the package install state, observe menu) and accept this gap until skill-runtime testing is established repo-wide (separate concern, not 123).

### Issues out of scope

9. **Module side-effect imports across the daytime_pipeline import chain.** Out of scope under the top-level-package probing decision (we never load `cortex_command.overnight.*` for the probe).
10. **Probe in worker-dispatched re-invocation.** Confirmed not relevant — workers don't invoke the lifecycle skill.

## Open Questions

All open questions have inline answers; nothing carries to Spec unresolved.

1. **Q (probe mechanism)**: Which probe(s) — `cortex --version` PATH check, import check, or both? Precedence?
   **A (Resolved)**: One probe — a `find_spec` import probe via `python3 -c`. The PATH check is redundant because the §1a dispatch path uses `python3 -m`, never the `cortex` binary. Probe target is the top-level `cortex_command` package (not `cortex_command.overnight.daytime_pipeline`) for ~80ms cost vs ~476ms. Form: `python3 -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('cortex_command') else 1)"`.

2. **Q (probe placement)**: SKILL.md (hoisted) vs implement.md §1 (just-in-time)?
   **A (Resolved)**: Just-in-time in `references/implement.md` §1 Pre-Flight Check, immediately before the `AskUserQuestion` call. Hoisting would tax research/specify/plan/review phases for no benefit; the autonomous-worktree feature is implement-phase-only. Placement matches the uncommitted-changes guard's location.

3. **Q (authoritative module name)**: Confirm `cortex_command.overnight.daytime_pipeline` is the truth.
   **A (Resolved)**: Confirmed. The body's "Scope" section uses `claude.overnight.daytime_pipeline` — that is a typo; the `claude.*` path does not exist in the repo. `skills/lifecycle/references/implement.md:71` and `cortex_command/overnight/daytime_pipeline.py` both confirm `cortex_command.overnight.daytime_pipeline`. Spec uses the `cortex_command.*` form.

4. **Q (prior art for runtime probes in markdown skills)**: Any existing pattern?
   **A (Resolved)**: None for runtime feature probes. The closest pattern is the uncommitted-changes guard at `skills/lifecycle/references/implement.md:17` — Bash call before `AskUserQuestion`, exit-code branching, fail-open fallback with diagnostic. This ticket establishes the runtime-probe pattern by re-using that guard's shape.

5. **Q (interaction surface)**: Does silent hide break anything (uncommitted-changes guard, events.log consumers, AskUserQuestion contract)?
   **A (Resolved)**:
   - Uncommitted-changes guard: independent — it demotes "Implement on current branch" in place (no removal). Probe removes "Implement in autonomous worktree". Different options, different mechanisms; they compose cleanly.
   - events.log consumers: the existing `implementation_dispatch`, `dispatch_complete`, `task_complete`, `phase_transition` events do not assume a specific menu shape — they record the chosen mode. Removing an option from the choice set produces no orphan events.
   - AskUserQuestion contract: 2 options is the minimum (`minItems: 2` on the options array). Two-option degrade is in-bounds. No spec-level conflict.

6. **Q (probe error fallback)**: Surfaced by the adversarial review — what happens if the probe subprocess itself errors?
   **A (Resolved)**: Fail-open. The guard does not fire (all three options shown), and a one-line diagnostic is surfaced alongside the prompt: e.g., `runtime probe skipped: python3 unavailable or import probe failed`. Matches the uncommitted-changes guard's `git status` failure handling. Rationale: a misconfigured user environment should not silently hide an option they may actually be able to use; the user-visible diagnostic gives them a thread to pull on.

7. **Q (drift atomicity)**: How are the two implement.md copies kept in sync?
   **A (Resolved)**: Source-of-truth is `skills/lifecycle/references/implement.md`. The build-plugin recipe regenerates `plugins/cortex-interactive/skills/lifecycle/references/implement.md` from source. The pre-commit hook (commit `79390c7`'s four-phase policy-aware drift enforcement) refuses commits where the staged plugin copy diverges from a freshly regenerated copy. Spec instructions: edit the source file, run `just build-plugin`, stage both, commit. The hook is an enforcement net, not a substitute for explicit two-file staging.
