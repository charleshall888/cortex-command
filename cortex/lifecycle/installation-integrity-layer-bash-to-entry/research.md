# Research: Promote ~13 bin/cortex-* scripts to wheel-tier Python entry points; add SessionStart PATH self-test

Backlog item: 252-installation-integrity-layer-bash-to-entry-point-migration-path-self-test-install-version-pin-probe
Parent epic: 251-harness-friction-triage-distribution-contracts-slugs-gates
Pin-probe scope wholly delegated to ticket 235.

## Codebase Analysis

### Shebang census (verified by Agent 5)

The 25 `bin/cortex-*` scripts split:

- `#!/usr/bin/env -S uv run --script` (PEP 723): 6 — `audit-doc`, `complexity-escalator`, `count-tokens`, `load-parent-epic`, `measure-l1-surface`, `resolve-backlog-item`
- `#!/usr/bin/env python3`: 9 — `archive-rewrite-paths`, `archive-sample-select`, `auto-bump-version`, `check-events-registry`, `check-parity`, `check-path-hardcoding`, `check-prescriptive-prose`, `commit-preflight`, `requirements-parity-audit`, `rewrite-cli-pin`
- bash: 10 — `backlog-ready`, `git-sync-rebase`, `invocation-report`, `jcc`, `lifecycle-counters`, `lifecycle-state`, `log-invocation`, `morning-review-complete-session`, `morning-review-gc-demo-worktrees`

Skill-prose-referenced bash subset: `backlog-ready`, `lifecycle-counters`, `lifecycle-state`, `morning-review-complete-session`. `cortex-lifecycle-state` is a non-trivial jq-based event-log reducer (`bin/cortex-lifecycle-state:22-30`); migration requires a Python re-implementation with parity guarantees against jq's tolerance of torn/malformed lines.

### Files that will change

- **`pyproject.toml`** lines 21–43 — add ~12 new `[project.scripts]` entries. Proposed name → module mapping (verify against existing module layout during plan): `cortex-auto-bump-version` → `cortex_command.auto_bump_version:main`, `cortex-backlog-ready` → `cortex_command.backlog.ready:main`, `cortex-check-parity` → `cortex_command.parity_check:main`, `cortex-check-prescriptive-prose` → `cortex_command.lint.prescriptive_prose:main`, `cortex-commit-preflight` → `cortex_command.commit.preflight:main`, `cortex-complexity-escalator` → `cortex_command.lifecycle.complexity_escalator:main`, `cortex-git-sync-rebase` → `cortex_command.git.sync_rebase:main`, `cortex-lifecycle-counters` → `cortex_command.lifecycle.counters:main`, `cortex-lifecycle-state` → `cortex_command.lifecycle.state_cli:main`, `cortex-load-parent-epic` → `cortex_command.backlog.load_parent_epic:main`, `cortex-morning-review-gc-demo-worktrees` → `cortex_command.overnight.gc_demo_worktrees:main`, `cortex-resolve-backlog-item` → `cortex_command.backlog.resolve_item:main`. (`cortex-morning-review-complete-session` is already promoted; exclude.)

- **New modules under `cortex_command/`** — one per promoted script. Argparse parser `prog` matches binstub name. Signature `main(argv: List[str] | None = None) -> int`. Preserve exit codes (0/2/3/64/70 for resolver class) and JSON-on-stdout / diagnostic-on-stderr contracts. `cortex_command/common.py` provides reusable helpers (`slugify()`, `_resolve_user_project_root()`, frontmatter-parsing idioms, `atomic_write`) — reuse rather than re-implementing.

- **`plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh`** — extend after line 29 (the `AUGMENTED_PATH=` augmentation) to run a PATH self-test. The self-test MUST `export PATH="$AUGMENTED_PATH"` inline before probing (the augmented PATH otherwise takes effect only on the next tool call via `$CLAUDE_ENV_FILE`, so a probe in the same hook would test the old PATH).

- **`bin/<promoted-name>`** — each promoted bash file is deleted or converted to a dual-channel wrapper (see §"Conventions" for the corrected wrapper template).

- **`skills/refine/references/clarify-critic.md:16,65,198`** and any other path-qualified `bin/cortex-<name>` references — must be updated in the same PR as the bin/ deletion. Pre-commit gate: `grep -rn 'bin/cortex-' skills/` must not surface deleted scripts. (Research from discovery noted this leaks into 253's scope if deferred; 252 should own it.)

### Reference patterns

- **Dual-channel wrapper template** — `bin/cortex-morning-review-complete-session:6-15` is the existing template, BUT it does not preserve the wheel-binstub-vs-working-tree escape hatch. When the wheel is installed, the wheel-import branch wins unconditionally; `CORTEX_COMMAND_ROOT` cannot force the working-tree branch. Migration must reorder branches to honor `CORTEX_COMMAND_FORCE_SOURCE=1` before the wheel-import probe. Without this, dogfooders iterating in the working tree without `--reinstall` between edits run stale wheel code.

- **Argparse + JSON contracts** — use `json.dumps(obj, separators=(",", ":"))` for compact form (matches `jq -c`). Insertion-order key ordering matches Python `dict` defaults from 3.7+; avoid `sort_keys=True` if downstream parsers care about ordering.

- **Sibling-script lookup pattern** — every existing `bin/cortex-*` invokes `"$(dirname "$0")/cortex-log-invocation"` as line 1–2. If `cortex-log-invocation` is promoted to a wheel entry point, this sibling-lookup breaks (the binstub lands in `~/.local/bin/`, not next to the calling script). Either promote `cortex-log-invocation` first and update siblings to `command -v cortex-log-invocation`, or keep `cortex-log-invocation` bash and exclude from this ticket.

### Integration points

- **`justfile`** lines 543–575 already rsync-mirror `bin/cortex-*` into `plugins/cortex-core/bin/`. No justfile change needed — dual-channel wrappers continue to mirror through transparently. The `build-plugin` recipe is unaffected.

- **`bin/cortex-check-parity`** validates that referenced bins have a wiring signal (skill/requirements/docs/hooks/justfile/tests reference). Existing checks remain valid for promoted scripts; `bin/.parity-exceptions.md` documents the three current exceptions (`cortex-archive-sample-select`, `cortex-batch-runner`, `cortex-pipeline-metrics` — all `library-internal`). Migration does not need new exceptions but may extend the schema (see Open Questions §3).

- **`bin/.events-registry.md`** — any promoted script emitting events must register them. `cortex-complexity-escalator` (registry line ~101) already shows the pattern.

- **`install_guard`** — Agent 5 verified: `cortex_command/__init__.py` is now a pure docstring; the install guard fires only from `cortex_command.cli._dispatch_upgrade` (`cortex_command/install_guard.py:7-12`). **The "defer cortex_command imports to function bodies" discipline cited in earlier research is stale**. Promoted modules may import freely at module load. The stale comment at `bin/cortex-resolve-backlog-item:31-36` referencing non-existent `__init__.py:13-15` should be removed during the promotion of that script.

- **Plugin hook layer (Layer 1)** — auto-update.md "Bash-tool subprocess carve-out" places the PATH self-test in the plugin tier, not the wheel. `plugins/cortex-core/hooks/cortex-session-start-path-bootstrap.sh` is the existing locus.

## Web Research

### `uv tool install` behavior on entry-point additions

- New `[project.scripts]` entries do NOT auto-take-effect on already-installed tools; require `uv tool install --reinstall`. Force-pushed git tags additionally need `--refresh` to invalidate uv's commit cache. Ticket 235's spec already adds `--refresh` to the `_run_install_and_verify` argv (235 req 15). ([uv tools concepts](https://docs.astral.sh/uv/concepts/tools/))
- Binstubs are symlinked into `~/.local/bin` on Unix (copied on Windows); the executable dir must be on PATH. uv prints a warning at install time and offers `uv tool update-shell` if missing.

### Migration patterns

- Three established patterns: full Python rewrite, thin Python wrapper subprocess-execing bash, hybrid. ([myByways](https://mybyways.com/blog/migrating-from-bash-shell-scripts-to-python), [bouzekri.net](https://blog.bouzekri.net/2017-10-08-bundle-cli-in-python-project.html))
- For already-Python (`#!/usr/bin/env python3` and PEP 723) source files, the subprocess-wrapper pattern pays interpreter-startup tax twice with no benefit. Full promotion (module + entry-point declaration) is the only pattern that fits.

### Doctor / PATH self-test patterns

- Standard pattern: `brew doctor`, `pyenv-doctor`, `rustup doctor`, `gh auth status` — exit 0, print advisories, never block the host. Anti-patterns: pyenv-on-shell-startup is broadly disliked for noise. Working pattern: silent on success, terse single-line on miss, never block.
- Anti-patterns to avoid: multi-line banners; color codes that survive pipes; advisories every session vs first-run gate; false positives during install-time PATH-sourcing race.

### Claude Code SessionStart hook contract (load-bearing caveats)

- Documented contract: stdout JSON `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<string>"}}`; cap 10,000 chars; overflow file-spilled with a preview. ([Claude Code hooks reference](https://code.claude.com/docs/en/hooks))
- Anthropic guidance: factual statements, not imperatives — imperative phrasing triggers prompt-injection defenses.
- **Known bug**: SessionStart JSON output silently dropped despite valid format and exit 0 ([claude-code#13650](https://github.com/anthropics/claude-code/issues/13650)) — ~1.3KB of valid JSON disappeared.
- **Known bug**: plugin-mode SessionStart hooks' `additionalContext` doesn't always surface to Claude ([claude-code#16538](https://github.com/anthropics/claude-code/issues/16538)).
- Implication: an advisory delivered only via additionalContext is unreliable. Belt-and-suspenders: write a sentinel file inside `cortex/` (sandbox-allowlisted) AND emit additionalContext.

### PEP 723 considerations

- PEP 723 is accepted, broadly tooled. Decision rule: if a script is invoked by other parts of the project, roll into the wheel; PEP 723 scripts require `uv run` invocation, which doesn't compose cleanly with PATH-based entry-point dispatch.

## Requirements & Constraints

### Architectural Constraints from `cortex/requirements/project.md`

- **CLI/plugin version contract (ADR-0002)** (line 39): "→ ADR-0002: CLI wheel + plugin distribution." Direct foundation for entry-point promotion.

- **Skill-helper modules** (lines 35–36): "Promoted modules expose a `[project.scripts]` console-script entry (e.g. `cortex-<skill>`) as the recommended invocation idiom; `python3 -m cortex_command.<skill> <subcommand>` is retained as a readable fallback." Endorses the migration pattern in this exact shape.

- **Wheel-binstub vs working-tree invocation** (lines 38–39, quoted verbatim): "When a Phase N commit edits `common.py` and a subsequent Phase N+1 step must invoke a binstub that reads `common.py` at runtime, Phase N's working-tree changes must be complete before invoking the binstub — the binstub reads the installed wheel, not the working tree. Use `python3 -m` invocation to run against the working tree when wheel reinstall between phases is not feasible." This constraint binds the dual-channel wrapper design.

- **SKILL.md-to-bin parity enforcement** (lines 33–34): "`bin/cortex-*` scripts wire through an in-scope SKILL.md/requirements/docs/hooks/justfile/tests reference. `bin/cortex-check-parity` blocks drift; exceptions at `bin/.parity-exceptions.md`."

- **Plugin-imports-zero-cortex-modules contract** (`docs/internals/mcp-contract.md:3-4`): "The MCP plugin imports zero `cortex_command.*` modules; its sole interface to the CLI is `subprocess.run(["cortex", ...])` plus parsing the versioned JSON the CLI emits on stdout." Binds the SessionStart hook side only — the migrating wheel modules are unaffected.

- **Events registry** (project.md line 41 and bin/.events-registry.md preamble): promoted scripts that emit events must be registered. Currently `cortex-complexity-escalator` is the only bash-source registration; pattern is established.

- **Per-repo sandbox registration (ADR-0003)** (line 31): The `cortex/` umbrella is the only `sandbox.filesystem.allowWrite` path. Self-test sentinel files must land under `cortex/` (e.g., `cortex/.cache/path-selftest.json`), NOT `~/.local/state` or `$XDG_STATE_HOME`.

- **Solution horizon** (line 21): "A scoped phase of a multi-phase lifecycle is not a stop-gap." The migration is durable architectural work, not a stop-gap.

### Two-layer architecture (`docs/internals/auto-update.md`)

- Bash-tool subprocess carve-out: PATH self-test belongs in plugin (Layer 1), not wheel (Layer 2). Hook execution is not gated by the MCP version-probe path; the self-test must defend against its own failure modes (exit 0 on any error).

### Parity exceptions

- `bin/.parity-exceptions.md` currently exempts three `library-internal` scripts. The schema is a candidate extension surface if the PATH self-test needs a `doctor-relevant: false` marker to avoid over-enumeration (see Open Questions §3).

## Tradeoffs & Alternatives

### Family A — Per-script migration shape

- **A1: Full Python promotion** — Move logic into `cortex_command/<area>/<name>.py` exposing `main()`; declare in `[project.scripts]`; leave a corrected dual-channel wrapper in `bin/`. Cost: low for already-Python scripts (6 PEP 723 + 9 stdlib-python = 15 of 25 are essentially module-move); medium for the 4 skill-referenced bash scripts (`backlog-ready`, `lifecycle-counters`, `lifecycle-state`, `morning-review-complete-session`); `cortex-lifecycle-state`'s jq event-log reducer needs careful parity work. Pattern alignment HIGH (matches the 22 existing entries). Closes DR4 cleanly. **Recommended.**

- **A2: Thin Python wrapper that subprocess-execs bash** — Each entry point shells back to the bash file. Cost: low per script; ~30–50ms subprocess fork overhead per call; doubles indirection. For already-Python scripts, pays interpreter-startup tax twice with no benefit. Pattern alignment LOW (no existing entry uses this). Useful only as a temporary bridge if logic translation must be deferred.

- **A3: Hybrid (full Python for structured/JSON; thin wrapper for trivial filters)** — Decision-rule overhead per new script; given the actual population is mostly Python-already, the hybrid degenerates to A1 with extra rules.

- **A4: Generated stubs from a manifest** — DR1 explicitly rejected this (introduces a second source of truth alongside `pyproject.toml`; undermines canonical-source-preservation).

### Family B — PATH self-test placement

- **B1: Extend `cortex-session-start-path-bootstrap.sh` in-place** — Append the self-test downstream of the existing line 29 PATH augmentation. One hook fork. Critical: must `export PATH="$AUGMENTED_PATH"` inline before probing (the env-file write takes effect on next tool call). **Recommended.**

- **B2: Sibling SessionStart hook in cortex-core** — Separation of concerns at the cost of a second hook fork + new hooks.json registration + new fixture. Mostly artificial separation given the hooks are tightly coupled (set PATH → check PATH worked).

- **B3: Sub-call inside ticket 235's hook** — Forbidden by 235 spec.md:60 ("cortex-core is not modified"). Inverse direction (a cortex-core hook in PARALLEL to 235's cortex-overnight hook) is architecturally permitted but has unspecified ordering (see Open Questions §4).

- **B4: `cortex --self-test` subcommand invoked from a thin hook** — Circular dependency: if `cortex` itself is the missing binary, the self-test cannot run. Doesn't work for the failure mode it's meant to catch.

### Family B enumeration sub-tradeoff

- **importlib.metadata source** — Returns all 22+ wheel-declared console_scripts including library-internal ones (`cortex-batch-runner`, `cortex-pipeline-metrics`). Naive use produces false-positive advisories.
- **253's grep enumeration** — Correct intersection: `set(entry_points) ∩ set(skill-prose-referenced)`. But binds 252 to 253's emission.
- **Extend `bin/.parity-exceptions.md` schema** — Add a `doctor-relevant` marker; self-test reads from there. Decouples 252 from 253.

### Family C — Migration breadth + sequencing

- **C1: All ~12 in one PR** — Large diff, high blast radius, hard to bisect.
- **C2: One script per PR (resolver first per DR4)** — 12 small PRs; high overhead.
- **C3: Two-phase — resolver PR first (DR4 proof-of-pattern), then bulk PR for the remaining ~11** — Establishes test scaffolding + binstub conventions in the first PR; bulk PR follows the template. **Recommended.**
- **C4: Tests paired with each promotion** — Convention rather than sequencing choice; applies regardless of how PRs are batched.

### Recommended approach

**A1 + B1 + C3 with C4 applied.** Rationale: Pattern alignment with the 22 existing entries; closes DR4; preserves the working-tree escape hatch via reordered dual-channel wrapper (CORTEX_COMMAND_FORCE_SOURCE=1 honored before wheel-import probe); avoids both the circular-dependency in B4 and the cross-plugin-coupling foreclosed by 235; gives reviewer a tractable two-PR cognitive load.

**What this gives up**: A1 commits to permanent removal of the `install_guard` boundary for promoted scripts — DR4 already endorses this for the resolver, but it generalizes. B1's single-hook choice gives up the optionality of disabling the self-test independently of the bootstrap (accepted — both are advisory-only).

## Adversarial Review

### Critical corrections found

- **Stale install_guard concern**: `cortex_command/__init__.py` is now pure docstring; install_guard fires only from `cortex_command.cli._dispatch_upgrade`. The "defer cortex_command imports" discipline cited in earlier research is unnecessary post-refactor. Stale comment at `bin/cortex-resolve-backlog-item:31-36` should be removed during promotion.

- **`cortex-jcc` not promotable**: It's a `just -f $CORTEX_COMMAND_ROOT/justfile` wrapper (`bin/cortex-jcc:24`). Promotion would require shipping the project's `justfile` as wheel data via `importlib.resources` and re-resolving — not in scope. Keep as bash.

- **`cortex-log-invocation` is load-bearing**: Every existing `bin/cortex-*` invokes `"$(dirname "$0")/cortex-log-invocation"` as line 1–2. If promoted, the sibling-script lookup pattern breaks for remaining bash scripts. Either promote it first and update siblings to `command -v cortex-log-invocation`, or keep it bash and exclude from this ticket.

- **Bootstrap-hook PATH timing**: `cortex-session-start-path-bootstrap.sh:31-32` writes augmented PATH to `$CLAUDE_ENV_FILE`, which takes effect on the next tool call. A probe in the same hook tests OLD PATH unless `export PATH="$AUGMENTED_PATH"` is executed inline first.

- **Sandbox writability**: `~/.local/state` is NOT in `sandbox.filesystem.allowWrite`. Sentinel file must live under `cortex/` (e.g., `cortex/.cache/path-selftest.json`).

- **Dogfooder false positives**: Working-tree `bin/` overrides wheel binstubs on PATH for dogfooders; `shutil.which` finds both with the same name but different semantics. Skip self-test when `CORTEX_DEV_MODE=1` OR `$CWD/pyproject.toml` declares `name = "cortex-command"`.

- **importlib.metadata over-enumerates**: A naive iteration over `entry_points(group='console_scripts')` flags `cortex-batch-runner` and `cortex-pipeline-metrics` as missing because they're invoked from inside Python, not from skill prose. Filter via either 253's grep (re-introduces dependency) or a new `doctor-relevant` column in `bin/.parity-exceptions.md`.

- **claude-code#13650 / #16538**: SessionStart additionalContext can be silently dropped. Belt-and-suspenders: write a sentinel file AND emit additionalContext.

- **Parity tests need fixtures**: A "parity test" against a deleted bash script must replay captured stdout/stderr/exit-code triples. Fixture generation (running the bash version pre-deletion across representative inputs) is an explicit per-script deliverable.

- **`bin/cortex-load-parent-epic` path-qualified references in skill prose**: Research from discovery flagged `skills/refine/references/clarify-critic.md:16,65,198` as hardcoding the bash path. 252 must update these in the same PR as the bash deletion; otherwise the dangling reference leaks into 253's scope.

### Failure modes still on the table

- **Race between `uv tool install --reinstall` and PATH refresh** — Narrow surface; rare; less critical than the in-hook PATH-source ordering described above.

- **Mixed-shebang nuance for parity tests** — PEP 723 scripts invoke `uv run --script` which creates an ephemeral venv from the inline metadata. The promoted wheel module skips the venv-creation step. Behavioral parity is structurally fine (the script's logic is the same), but startup latency differs measurably; benchmarks would surface this only if a script is in a hot loop.

## Open Questions

1. **`cortex-log-invocation` promotion or exclusion** — Promoting it breaks the `"$(dirname "$0")/cortex-log-invocation"` sibling pattern in remaining bash scripts. Two options: (a) promote it as the first script in the 252 sequence AND update every remaining bash sibling to `command -v cortex-log-invocation`; (b) keep `cortex-log-invocation` bash-only and out of 252's promotion list. Decision is a Spec interview item.

2. **Atomic-promotion of `cortex-jcc`-like wrappers** — `cortex-jcc` cannot be promoted (needs working-tree `justfile`). Should it be parity-allowlisted as `dogfooder-only` and never appear in the self-test's expected-binary list? Spec interview item.

3. **Enumeration source for the PATH self-test — three candidates**:
   - (a) `importlib.metadata.entry_points(group='console_scripts')` filtered against `bin/.parity-exceptions.md` (extend the file's schema with a `doctor-relevant: false` marker for library-internal entries).
   - (b) Wait for 253 to emit its skill-prose grep enumeration and consume that artifact at hook time.
   - (c) Hand-maintained allow-list inside the hook itself (drift risk; rejected by Agent 4 implicitly).
   Recommendation from research: (a) decouples 252 from 253 cleanly; the marker extension is small. Spec interview item.

4. **Ordering between cortex-core's new self-test hook and cortex-overnight's 235 drift-detector hook at SessionStart** — Both run at session start. The bootstrap hook's PATH augmentation must take effect before either tests PATH. If the self-test lives INSIDE the bootstrap (B1), this is internal sequencing. If split (B2), the ordering between two plugins' SessionStart hooks is unspecified by Claude Code's `hooks.json` schema. Recommendation: B1 (in-place extension) sidesteps the ordering risk entirely.

5. **Wheel-binstub-vs-working-tree escape hatch** — Adding `CORTEX_COMMAND_FORCE_SOURCE=1` to the dual-channel wrapper is a new contract that should be documented in project.md's "Wheel-binstub vs working-tree invocation" section. Spec must decide whether the docs update is in 252's scope or splits to a docs-only follow-up.

6. **Parity-test fixture generation strategy** — Per-script captured triples committed to `tests/fixtures/<script-name>/`. For `cortex-lifecycle-state` (input space = arbitrary `events.log` content) and `cortex-backlog-ready` (whole-backlog state-dependent), fixture coverage is non-trivial. Spec must define which input slices are golden.

## Considerations Addressed

- **Phase-N+1 binstub read of migration-target scripts within a lifecycle (wheel-binstub-vs-working-tree constraint)** — Addressed. The dual-channel wrapper as currently shipped (`bin/cortex-morning-review-complete-session`) does NOT preserve the working-tree escape hatch; the wheel-import branch wins unconditionally. Mitigation: reorder the wrapper to honor `CORTEX_COMMAND_FORCE_SOURCE=1` before the wheel-import probe. Open Question #5 carries the project.md docs-update decision into Spec.

- **Artifact shape ticket 253 emits and how 252's PATH self-test binds to it** — Addressed. Three enumeration sources surfaced (importlib.metadata + parity-exceptions filter; 253's grep artifact; hand-maintained list). The importlib.metadata + extended parity-exceptions approach decouples 252 from 253 cleanly. Open Question #3 carries the final choice into Spec.

- **Whether 252 can ship before 253 and what the fallback is** — Addressed. 252 can ship before 253 by adopting the importlib.metadata + `bin/.parity-exceptions.md` schema-extension approach. The parent epic's "ship in any order" claim survives; the child's previously-described 253 dependency is reduced to a soft (preferred-but-not-required) coupling.
