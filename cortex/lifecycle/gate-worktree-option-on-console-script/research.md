# Research: Gate worktree option on console-script reachability, not bare-Python importability

## Scope (clarified intent)

Replace the bare-Python `cortex_command` importability probe currently guarding the lifecycle implement-phase "worktree" menu option with a console-script reachability check, AND add a class-level lint rule preventing bare-Python `cortex_command` imports in skill files. Two coupled deliverables:

1. **Gate-signal swap**: §1 probe changes from `python3 -c "...importlib.util.find_spec('cortex_command')..."` to a PATH-based reachability check against a console-script that exposes the worktree-creation surface. The §1a worktree-creation sub-flow itself must align with whatever surface the gate detects, so gate and gated path agree on what "available" means.
2. **Class-level lint rule**: a structural guard in `cortex_command/lint/` that catches every shape of bare-Python `cortex_command.*` import in `skills/**/*.md` (single-line `python3 -c`, multi-line `python3 -c "\n..."`, heredoc `python3 <<EOF`, fenced ```python blocks invoked by `python3`), with sentinel-suppression for legitimate references.

Both scopes are mandatory; the existing literal-substring grep from the precedent lifecycle (`'python3 -c "import cortex_command'` at `cortex/lifecycle/convert-bin-cortex-and-skill-embedded/spec.md` R15/R17) already failed to catch the §1a regression in `implement.md:126`, so a class-level rule is the only durable fix.

## Codebase Analysis

### Files that will change

- `skills/lifecycle/references/implement.md:55-66` — §1 runtime probe block. The bare `python3 -c` heredoc with `importlib.util.find_spec('cortex_command')` is replaced with a PATH-based reachability check against the new console-script.
- `skills/lifecycle/references/implement.md:123-128` — §1a step iii. The fenced ```python block (`from cortex_command.pipeline.worktree import create_worktree; info = create_worktree(...)`) is replaced with a Bash call to the same console-script the gate probes, invoking it in worktree-create mode.
- `plugins/cortex-interactive/skills/lifecycle/references/implement.md` — regenerated mirror; the four-phase drift-enforcement pre-commit hook (`just build-plugin` + dual-source enforcement) refuses commits where the staged plugin copy diverges. Both copies update together.
- `pyproject.toml` `[project.scripts]` — adds one new entry exposing `cortex_command.pipeline.worktree.create_worktree` as a console script (recommended name and shape in Synthesis below).
- `cortex_command/pipeline/worktree_cli.py` (new) OR a new subcommand on an existing module — the actual console-script entry point. Module choice is in Synthesis.
- `cortex_command/lint/` — new module (`bare_python_import.py` or equivalent) implementing the class-level lint rule. Reuses the fence state machine from `cortex_command/lint/contract.py` and the `--staged` / `--audit` mode shape from both existing lint modules.
- `bin/cortex-check-bare-python-import` (new shim) OR an extension of `cortex-check-contract` — choice surfaced in Synthesis.
- `tests/test_check_bare_python_import.py` (new) — positive/negative fixture coverage following the shape of `tests/test_check_contract.py` and `tests/test_check_prescriptive_prose.py`.
- `tests/test_implement_worktree_interactive_contract.py` — extended (or paired with a new test) to assert the new structural marker (PATH-based probe substring) is present in §1 and the §1a console-script invocation matches.
- `.githooks/pre-commit` and/or `justfile` — wire the new lint into the pre-commit critical path alongside `cortex-check-contract --staged` and `cortex-check-prescriptive-prose --staged`.
- `bin/.contract-lint-exceptions.md` (or sibling ledger) — possibly extended if the new lint reuses the exception-ledger pattern; not strictly required if the new rule has a per-line `<!-- ignore-next -->` sentinel.

### Relevant existing patterns

**Console-script reachability check (already canonical in the codebase):**

- `bin/cortex-complexity-escalator:13`, `bin/cortex-auto-bump-version:9`, `bin/cortex-check-parity:11`, `bin/cortex-check-contract:11`, `bin/cortex-jcc:8` and ~10 other bin/ wrappers gate on `command -v cortex-log-invocation >/dev/null 2>&1`. This is the in-repo standard for "is the console-script reachable in the calling shell."
- `skills/lifecycle/references/complete.md:212-218` — the only skill-prose precedent uses `command -v cortex-update-item` and `command -v cortex-generate-backlog-index` as availability gates for graceful-degrade fallback. The pattern is "separate Bash tool call using `test -f` or `command -v` to check availability before running."
- `cortex_command/auth/bootstrap.py:49`, `cortex_command/doctor/path_self_test.py:198`, `cortex_command/overnight/scheduler/macos.py:888` — the Python-side equivalent uses `shutil.which("<binary>")` against PATH.
- `cortex_command/parity_check.py:430-491` — the parity gate already treats `command -v <cortex-binary>` and `uv run <cortex-binary>` as canonical invocation patterns (regex `\b(?:uv run|command -v)\s+(cortex-[a-z][a-z0-9-]*)`), so adding a new console-script + a `command -v` callsite in `implement.md` is on-grain with the parity contract.

**Console-script entry-point precedent (sibling to the worktree wrap):**

- `cortex_command/pipeline/worktree_resolve_cli.py` is a thin wrapper that exposes `cortex_command.pipeline.worktree.resolve_worktree_root` as the `cortex-worktree-resolve` console-script. Existing template — short module, single `main()`, prints to stdout, exits 0/2. The worktree-create wrapper would mirror this shape exactly.

**Lint infrastructure (the class-level rule's home):**

- `cortex_command/lint/contract.py` (1669 lines) implements: fence state machine (handles ```/~~~ delimiters of length ≥3, backslash continuation inside fenced blocks, captures the non-blank line preceding the opening fence), inline-code span scanner (` `…` `), `<!-- contract-lint:ignore-next -->` sentinel suppression (`_SENTINEL_RE` at line 1157), exception-ledger pattern (`bin/.contract-lint-exceptions.md`), staged/audit modes via argparse, CLI with `--staged`, `--audit`, `--json`, `--self-test`, `--validate-exceptions`.
- `cortex_command/lint/prescriptive_prose.py` (411 lines) implements: section-scoped scanner (only flags inside specific markdown sections), separate fence state machine, file-discovery + git-staged path filtering.
- Both modules are stdlib-only, AST/regex-based, and follow a `scan_text(text, path) -> list[Violation]` shape that's trivial to extend.

**Skill-text scan corpus:**

- `_SCAN_GLOBS` in `contract.py:419-427` covers `skills/**/*.md`, `hooks/**`, `justfile`, `docs/**/*.md`, `tests/**/*.md`, `CLAUDE.md`, `cortex/requirements/**/*.md` — exactly the corpus the new lint should target (the precedent grep covered only `skills/lifecycle/references/implement.md` and `skills/critical-review/references/residue-write.md`, hence the regression).
- Hard exclusions (`_HARD_EXCLUDE_PREFIXES`) cover `cortex/research/archive/`, `cortex/lifecycle/`, and `tests/fixtures/contract/` — the lifecycle-archive exclusion is important so archived spec.md files (which document the old bad pattern) don't trigger.

### Integration points and dependencies

- The `cortex_command.pipeline.worktree.create_worktree` function (`worktree.py:170-249`) is the API the §1a sub-flow invokes today via bare-Python import. Signature: `create_worktree(feature: str, base_branch: str = "main", repo_path: Path | None = None, session_id: str | None = None) -> WorktreeInfo`. Already used by `cortex_command/pipeline/dispatch.py` and friends; not currently console-script-wrapped.
- The `interactive-` prefix is the load-bearing convention — `create_worktree` calls `_resolve_branch_name(feature, repo, prefix=...)` and a feature name starting with `interactive-` resolves to the `interactive/<slug>` branch.
- The parity gate (`cortex_command/parity_check.py`) treats `[project.scripts]` keys + `bin/` exec files as the deployed set; adding a new entry and (optionally) a wrapper script is on-grain.
- The pre-commit hook (`.githooks/pre-commit`) is the natural enforcement chokepoint for the new lint. Today it runs `cortex-check-contract --staged` and `cortex-check-prescriptive-prose --staged` (confirmed by their `--staged` mode shape and `_staged_paths` helpers).

### Conventions to follow

- New console-script: register in `pyproject.toml [project.scripts]` AND create a thin CLI module under `cortex_command/pipeline/` (or wherever the wrapped function lives). Console-script names use kebab-case (`cortex-worktree-create-check`, not `cortex_worktree_create_check`).
- Adding `[project.scripts]` entries requires `uv tool install -e . --force` per the pyproject.toml header comment (lines 25-27) — document in CHANGELOG and verify-step.
- New lint follows existing module shape: stdlib-only, `Violation` dataclass with `path/line/col/code/message`, separate `--staged` and `--audit` modes, sentinel-suppression for legitimate references.
- New CLI module must follow R14 from the precedent lifecycle (sibling-lint-compatible): single `argparse.ArgumentParser` at module scope or inside `main()` to avoid E202 ambiguous-parser.
- Telemetry call (`_telemetry.log_invocation`) at top of `main()` per the precedent lifecycle's R22 — required for `bin/cortex-invocation-report --check-entry-points` to pass.
- Dual-source enforcement: any edit to `skills/lifecycle/references/implement.md` requires `just build-plugin` to regenerate `plugins/cortex-interactive/skills/lifecycle/references/implement.md`; the four-phase pre-commit hook refuses divergence.
- Add a structural-contract test pattern (per `tests/test_implement_worktree_interactive_contract.py`) for the gate's structural marker — pins the substring the parity test anchors against so future drift fails CI rather than silently regressing.

## Defense-of-current: PATH-based console-script reachability

### Candidate mechanisms (cross-shell portability)

The codebase exclusively uses two mechanisms for "is a binary reachable":

1. **`command -v <name> >/dev/null 2>&1`** — POSIX-builtin, requires nothing on PATH itself. Returns 0 if `<name>` is found as a builtin, function, alias, or executable on PATH. The de-facto standard in `bin/` wrappers and `skills/lifecycle/references/complete.md`. Per the [Bash Hackers Wiki](https://wiki.bash-hackers.org/scripting/nonportable) and [Hynek's TIL](https://hynek.me/til/which-not-posix/), `command -v` is the only POSIX-mandated form among the three common alternatives (`command -v` / `which` / `hash`).
2. **`shutil.which("<name>")`** — Python-side equivalent, used inside `cortex_command/` modules where the reachability check happens inside Python rather than bash.

`which` is explicitly NOT used — it's not POSIX, on Debian it's a shell script in the optional `debianutils` package, and on different distros it has different output formats. `hash <name>` is POSIX but has a side effect (populates the shell's command hash table) and isn't a common pattern in this repo.

### Mechanism evaluation

For the §1 gate, `command -v <binary> >/dev/null 2>&1` is the clear winner across the four dimensions:

(a) **Cross-shell portability**: `command -v` is POSIX-mandated for every conformant shell (bash, zsh, dash, ash, busybox sh). The lifecycle skill's Bash tool runs commands through the user's shell, which is one of those on every documented install platform.

(b) **False-positive risk** (script exists but env is broken): low. `command -v` only confirms PATH resolution; it doesn't confirm the script's interpreter can find its own dependencies. But for a `uv tool install`-installed console script, PATH presence implies the wrapper script exists, the venv exists, and the entry-point module is importable — the wrapper IS the venv-bound dispatch shim. The only failure mode after PATH-resolution is the wrapper finding a corrupted venv, which `command -v` cannot detect. This is the same residual risk the existing `command -v cortex-log-invocation` checks in `bin/cortex-*` accept.

(c) **False-negative risk** (script reachable via direct path but not in PATH): low for the gate's stated purpose. The clarified intent says the gate signal must "hold across both source-tree development and the documented uv-tool install topology." Both topologies put `cortex-*` scripts on PATH after install (uv-tool via `uv tool update-shell`; source-tree dev via `uv tool install -e . --force`). A user who has the venv but no PATH wiring is in an explicitly-undocumented broken state — the existing graceful-degrade spec is the precedent for treating that as the user's broken install, not the skill's responsibility to mask.

(d) **Implementation cost**: trivial. One Bash call replacing the current 7-line `python3 -c` heredoc. The §1a sub-flow becomes a Bash call to the same binary instead of a fenced ```python block — net reduction in skill prose.

**Recommendation: `command -v <binary> >/dev/null 2>&1`** with exit-code routing:
- exit 0 → binary reachable → all three options remain.
- exit 1 → binary unreachable → remove the worktree option silently (preserves graceful-degrade intent from the archived spec).
- any other exit (shell-error, e.g., 127 for `command` itself missing) → fail-open with diagnostic `worktree gate skipped: command -v probe failed` (mirroring the existing fail-open precedent and the `uncommitted-changes guard skipped:` shape at implement.md:53).

The strongest "presence implies downstream success" guarantee: because the §1a sub-flow will invoke THE SAME binary the gate detects, a passing gate structurally guarantees the gated path's invocation surface is callable. This is the symmetry the clarified intent demands ("gate and gated path must agree on what 'available' means").

## Failure-of-alternative: alternative probe shapes and entry-script choices

### Alternative 1: Dry-run an existing console script

Could the gate just run `cortex-worktree-resolve interactive-probe --check` (or invent a `--check` flag on an existing binstub) instead of adding a new entry? Three problems:

(a) `cortex-worktree-resolve` exists and is on-PATH for any `uv tool install`-installed consumer, but it wraps `resolve_worktree_root`, not `create_worktree` — a passing `cortex-worktree-resolve --check` doesn't guarantee `create_worktree` is reachable. The two functions live in the same `cortex_command.pipeline.worktree` module today, so importability is co-extensive, but the gate's job is to detect the surface the §1a sub-flow USES, not a sibling surface that happens to import from the same module. **Rejection rationale**: violates the symmetry constraint — gate and gated path would be different binaries.

(b) Adding a `--check` flag to `cortex-worktree-resolve` couples two unrelated concerns (path resolution and create-availability probe) into one script. The same critic-pattern the precedent lifecycle's Non-Requirements rejected (consolidation of `cortex-lifecycle-config` and `cortex-critical-review-residue`) applies here: noun-group coherence is shallow. **Rejection rationale**: oversells the coherence of two unrelated operations.

(c) Latency: any `cortex-*` invocation pays the Python-interpreter startup cost (~80-200ms for `find_spec`, ~250-500ms for full module import per the archived spec's measurements). A `command -v` check costs ~1ms. The current `python3 -c` probe is in the ~80ms range; the gate runs once per §1 render. Substituting `command -v` is a >50x latency improvement on every implement-phase entry. **Rejection of dry-run probes on latency grounds is decisive** — a `cortex-worktree-create --check` that does Python-side validation would be slower than the current probe.

### Alternative 2: Extend an existing `cortex-*` binstub with a subcommand vs. add a dedicated binstub

Two specific candidates:

- **Extension**: add `cortex worktree create` as a subcommand under the unified `cortex` CLI (already wired via `cortex_command/cli.py`). The `cortex` CLI's subcommand pattern is established (the `overnight` group is fully wired; other groups are stubbed with `_make_stub` per `cli.py:33-40`).
- **Dedicated binstub**: add `cortex-worktree-create` as a sibling to `cortex-worktree-resolve`.

The precedent lifecycle (`convert-bin-cortex-and-skill-embedded`) explicitly considered and rejected the `cortex <group> <verb>` subcommand wiring approach (its Non-Requirements: "No `cortex <group> <verb>` subcommand wiring added to `cortex_command/cli.py`. Rejected per the symmetric-defense re-evaluation in research: the four skill helpers are not a coherent noun-group like `git remote *`; they are sequenced inline-flow predicates"). The same logic applies here: `cortex-worktree-create` is a sequenced inline-flow operation invoked from §1a, not a member of a coherent `cortex worktree *` noun-group.

**Recommendation: dedicated `cortex-worktree-create` binstub**, mirroring the shape of `cortex-worktree-resolve`. Pros: (i) the gate's `command -v cortex-worktree-create` and the §1a invocation `cortex-worktree-create --feature interactive-<slug> --base-branch main` use the same binary — perfect symmetry; (ii) follows the established convention (every `cortex_command/pipeline/*` module that the skill prose touches has its own `*_cli.py` wrapper); (iii) avoids the noun-group fiction the precedent lifecycle rejected.

### Alternative 3: PATH presence + dry-run combination

Should the gate probe consist of "binstub on PATH" PLUS "binstub returns exit 0 on a no-op invocation" (e.g., `cortex-worktree-create --check`)? Rejected on two grounds:

(a) Latency: ~250ms (Python interpreter startup) × every §1 render. The whole point of replacing the bare-Python probe is to remove the interpreter-startup tax.

(b) Diminishing returns: PATH presence already implies the venv exists and the wrapper script can boot to the entry-point. The marginal coverage of "wrapper boots but the create function crashes" is small, and any such crash would surface immediately in §1a anyway — the gate doesn't need to predict every failure mode of the gated path, only to suppress the option in the "binary absent" class.

**Recommendation**: gate is PATH presence only. The §1a invocation is the ground-truth check; if it fails, the existing `create_worktree` failure handling (raises `ValueError`, surfaced at `implement.md:132`) catches it.

### Console-script entry shape

The new `cortex-worktree-create` binstub should:

- Accept `--feature <name>` (required), `--base-branch <name>` (default `main`).
- Wrap `create_worktree(feature=<feature>, base_branch=<base_branch>)` — no `repo_path` / `session_id` exposed (those are cross-repo concerns, not interactive-worktree concerns).
- On success, print the resolved worktree path to stdout (mirrors `cortex-worktree-resolve`'s output shape) — the §1a sub-flow consumes this for the §1a step iv pre-flight check (`worktree_path = Path(resolved.stdout.strip()).resolve()`).
- On `ValueError` from `create_worktree`, print the error to stderr and exit 2.
- Telemetry call at top of `main()` per R22 from precedent lifecycle.

This shape lets §1a step iii become a single Bash call: `cortex-worktree-create --feature interactive-{slug} --base-branch main` — eliminating the fenced ```python block entirely.

## Lint rule shape: class-level guard against bare-Python `cortex_command` imports in skill files

### Why the precedent grep fails

The precedent lifecycle (`convert-bin-cortex-and-skill-embedded` R15/R17) used `grep -c 'python3 -c "import cortex_command' <file>` as its verification. This pattern fails the §1a regression at `implement.md:126` because:

(a) The pattern requires the literal substring `python3 -c "import cortex_command` — but the §1a snippet is a fenced ```python block (no `python3 -c` prefix), invoked via bare python3 from the surrounding bash context.

(b) The pattern is a literal-substring grep — it doesn't match `python3 -c "\nimport cortex_command\n..."` (multi-line), `python3 <<EOF\nimport cortex_command\nEOF` (heredoc), or `python3 -c 'from cortex_command...'` (single-quoted variant).

(c) Coverage scope: the precedent grep only ran against two specific files (`skills/lifecycle/references/implement.md`, `skills/critical-review/references/residue-write.md`) — a class-level rule needs to scan the full skill corpus and any new skill file that ships.

### Detection pattern shapes that must be caught

The new lint must flag every one of:

1. **Single-line `python3 -c "..."`** with `import cortex_command` or `from cortex_command.* import ...` inside the quoted Python string.
2. **Multi-line `python3 -c "..."`** where the quoted string spans multiple lines (the current §1 probe uses this shape — `python3 -c "\nimport sys\ntry:\n    import importlib.util\n...\n"`).
3. **Heredoc-fed `python3 - <<EOF`** or `python3 <<'EOF'` where the heredoc body contains `import cortex_command` (the §1a:137 `python3 - <<'EOF'` pre-flight check uses this shape, though that one imports stdlib only and is legitimate).
4. **Fenced ```python blocks** that follow context-implying bare-python invocation (the §1a:123-128 case — a fenced ```python block in implement.md whose prose says "Single Bash call invoking `create_worktree`" but the model dispatches it via bare python3 because no console-script wrapper exists).
5. **Bash variable assignment** like `result=$(python3 -c "from cortex_command...")` — variant of (1) inside command substitution.

### Non-false-positive cases (the lint must NOT flag)

- Console-script invocation: `cortex` or `cortex-*` callsites that don't shell out to `python3`.
- Commentary about `cortex_command` in prose: "The CLI calls `cortex_command.lifecycle_config.read_branch_mode`" at `implement.md:32` is narrative reference, not invocation. The contract-lint precedent's inline-backtick stripping (`_strip_inline_backticks` in prescriptive_prose.py) handles this.
- `python3 -m cortex_command.<module>` invocations (these are valid in the `cortex_command/` source-tree; the policy is about bare `python3 -c` import smuggling, not `python3 -m` module dispatch).
- `python3 -c` invocations that import only stdlib modules (the §1a:137 pre-flight uses `python3 - <<'EOF'` for path-traversal validation with only `subprocess`, `sys`, `pathlib.Path` — entirely stdlib).
- `python3 -c` invocations in `_interactive_overnight_check.sh` that import only `json`, `sys` (stdlib JSON parsing).
- Hard-excluded paths: `cortex/lifecycle/archive/` (documents the old bad pattern); `cortex/research/archive/`; `tests/fixtures/contract/` (intentional violation fixtures).

### Cleanest detection pattern

The detection has two natural shapes; both are viable.

**Shape A: regex on the (bash-context, python-body) pair across multi-line.**

A regex/state-machine that finds every `python3 -c` callsite (including multi-line, heredoc, fenced) and inspects the Python body for `\b(?:import\s+cortex_command|from\s+cortex_command(?:\.[a-z_][a-z0-9_]*)*\s+import)\b`. Implementation: extend the fence state machine in `cortex_command/lint/contract.py` (which already handles multi-line fences with backslash continuation, heredoc-like blocks, and the preceding-line sentinel) to also recognize:

- `python3 -c "..."` spans (single-line, including escape-aware quoting).
- `python3 -c "..."` spans split across continuation lines with `\` at EOL.
- Heredoc bodies: `python3 - <<['"]?EOF['"]?` opener through matching `^EOF$` line.
- Fenced ```python blocks preceded by bash context that implies python3 invocation.

For each captured python-body region, run the regex above. Emit violation if matched and not suppressed by sentinel.

**Shape B: two-pass scan — find python3 callsites, then sub-scan their bodies.**

Pass 1: find all `python3` invocation spans using a state machine. Pass 2: lex each span's python-body region and AST-parse it (or regex-match the import statements). The advantage of AST-parsing is precision — `import cortex_command` is unambiguously detected without false-matching `cortex_command` mentioned in a comment or string literal. The cost is two-pass complexity and a dependency on the python body being parseable (which it must be, or it would already be broken in production).

**Recommendation: Shape A with regex on the python-body region.** Rationale:

- The fence state machine in `cortex_command/lint/contract.py` is already battle-tested and handles the hard cases (multi-line fences, backslash continuation, sentinel scoping).
- AST-parsing is overkill: `cortex_command` mentioned in a comment inside a python3 body is itself a code smell (why is a skill file's python-body discussing internal modules in comments?). False positives in that edge case are acceptable.
- The regex `\b(?:import\s+cortex_command|from\s+cortex_command(?:\.[a-z_][a-z0-9_]*)*\s+import)\b` is precise enough; bash-quote escaping is handled by the state machine's span extraction.

### Module home

Three options:

1. **Extend `cortex_command/lint/contract.py`** with the new rule as a new error code (e.g., `E105 bare-Python cortex_command import in skill prose`). Pros: reuses existing fence machinery, sentinel handling, exception-ledger pattern. Cons: contract.py is already 1669 lines and its docstring scopes it to "AST-based argparse surface extractor for cortex-* console scripts" — adding a structurally different concern blurs the module's purpose.
2. **New module `cortex_command/lint/bare_python_import.py`**, sibling to `contract.py` and `prescriptive_prose.py`. Pros: clean separation of concerns; mirrors the precedent of `prescriptive_prose.py` (which spun off as its own concern from a generic prose lint). Cons: duplicates fence state-machine code (the contract.py fence machinery is 200+ lines).
3. **Extract a `cortex_command/lint/_fence.py` shared module** and have both `contract.py` and the new `bare_python_import.py` import from it. Pros: eliminates duplication, makes future lints cheaper. Cons: a refactor on top of a new feature — violates the favor-long-term-but-not-now principle from CLAUDE.md if the duplication is one-time.

**Recommendation: option 2 (new sibling module)** with a comment in the new module's docstring noting the fence-state-machine duplication as a deliberate near-term choice. Rationale:

- The lint rule is conceptually distinct from the argparse-surface-extractor — bundling them would violate the module-purpose principle.
- The prescriptive-prose lint already duplicates a (simpler) fence state machine in `prescriptive_prose.py:115-156`, so the duplication is already an accepted pattern.
- A future "extract shared fence module" lifecycle can fold both consumers if/when a third lint needs it (rule of three). For now, two consumers don't justify the refactor.
- The CLI shim is a new `bin/cortex-check-bare-python-import` mirroring `bin/cortex-check-contract` / `bin/cortex-check-prescriptive-prose` — telemetry call at top, single `main()` dispatch.

### Test-coverage surface

Following the shape of `tests/test_check_contract.py` and `tests/test_check_prescriptive_prose.py`, the new lint needs:

**Positive cases (must flag):**

- Single-line `python3 -c "import cortex_command"`.
- Single-line `python3 -c "from cortex_command.pipeline.worktree import create_worktree"`.
- Multi-line `python3 -c "..."` with embedded newlines that contain `import cortex_command`.
- Heredoc `python3 - <<EOF\nimport cortex_command.pipeline\n...\nEOF`.
- Heredoc with quoted delimiter `python3 - <<'EOF'\nfrom cortex_command import ...\nEOF`.
- Fenced ```python block (e.g., the current §1a:123-128 shape).
- Inside `$(python3 -c "...")` command substitution.

**Negative cases (must NOT flag):**

- `python3 -m cortex_command.<module>` (module dispatch, not bare import).
- `python3 -c "import json; print(json.loads(...))"` (stdlib-only, no cortex_command).
- Prose: "The CLI calls `cortex_command.lifecycle_config.read_branch_mode`" (narrative inline-code reference).
- Inline `cortex_command.pipeline.worktree.create_worktree` mentioned in a fenced markdown block without `python3` invocation.
- `cortex` or `cortex-*` console-script invocations.
- Hard-excluded paths: `cortex/lifecycle/archive/`, `cortex/research/archive/`, `tests/fixtures/<lint>/` fixtures.
- Sentinel-suppressed cases: line preceded by `<!-- bare-python-lint:ignore-next -->` (or equivalent sentinel — name to align with the lint's own ID).

**Integration test:** running the lint against the current corpus (after the gate-swap and §1a fix) must exit 0. Running it against a fixture containing the pre-fix `implement.md:123-128` shape must exit non-zero with a violation pointing at the fenced ```python block.

## Synthesis: recommended approach

### (a) New console-script entry

**`cortex-worktree-create`** as a dedicated `[project.scripts]` entry wrapping `cortex_command.pipeline.worktree.create_worktree`:

```toml
cortex-worktree-create = "cortex_command.pipeline.worktree_create_cli:main"
```

New module `cortex_command/pipeline/worktree_create_cli.py` mirroring the shape of `worktree_resolve_cli.py`:
- Accepts `--feature <name>` (required), `--base-branch <name>` (default `main`).
- Calls `create_worktree(feature=<feature>, base_branch=<base_branch>)`.
- On success, prints `info.path` to stdout (matching the `cortex-worktree-resolve` output convention).
- On `ValueError`, prints to stderr and exits 2.
- Telemetry call at top of `main()`.
- Single `argparse.ArgumentParser` (sibling-lint-compatible per R14).

### (b) Gate probe mechanism

Replace the `python3 -c "...find_spec('cortex_command')..."` block at `implement.md:55-66` with:

```bash
command -v cortex-worktree-create >/dev/null 2>&1
```

Exit-code routing (preserves the archived graceful-degrade spec's three-disposition contract):
- **exit 0** → binary reachable → all three options remain.
- **exit 1** → binary unreachable → remove "Implement on feature branch with worktree" from options array; silent hide (no diagnostic).
- **any other exit** (e.g., 127 if `command` itself is missing — vanishingly unlikely on any POSIX shell) → fail-open: all three options remain, diagnostic `worktree gate skipped: command -v probe failed` surfaced alongside the prompt.

### (c) §1a sub-flow invocation surface

Replace the fenced ```python block at `implement.md:123-128` with a single Bash call:

```bash
cortex-worktree-create --feature interactive-{slug} --base-branch main
```

The §1a sub-flow continues to consume the printed worktree path (stdout) for the step iv pre-flight check (which already shells out to `cortex-worktree-resolve` to get the path — both binaries print the same path-shape, so consumption is uniform).

Gate and gated path now share the same binary; the symmetry constraint from the ticket's Integration section is structurally satisfied.

### (d) Lint rule home + detection pattern

**Home**: new module `cortex_command/lint/bare_python_import.py` + CLI shim `bin/cortex-check-bare-python-import` + pre-commit-hook wiring alongside the existing contract / prescriptive-prose lints.

**Detection pattern**: fence-state-machine + regex on python-body regions:

- Scan corpus: `skills/**/*.md`, `hooks/**`, `docs/**/*.md`, `tests/**/*.md`, `CLAUDE.md` (mirror `contract.py`'s `_SCAN_GLOBS`).
- Hard exclusions: `cortex/lifecycle/archive/`, `cortex/research/archive/`, `tests/fixtures/bare_python_import/` (for self-test fixtures).
- For each file, walk lines tracking: in-python-body state (active inside `python3 -c "..."` spans including multi-line; inside heredoc bodies `python3 - <<['"]?EOF['"]?` ... `^EOF$`; inside fenced ```python blocks whose preceding context indicates bare-python dispatch).
- For each captured python-body region, regex-match: `\b(?:import\s+cortex_command|from\s+cortex_command(?:\.[a-z_][a-z0-9_]*)*\s+import)\b`. Emit `Violation(path, line, col, code="L201", message="bare-Python cortex_command import in skill prose — use console-script invocation instead")` on match.
- Sentinel suppression: `<!-- bare-python-lint:ignore-next -->` on the immediately preceding non-blank line suppresses the next violation (per the contract.py precedent at `_SENTINEL_RE:1157`).
- CLI: `--staged` (pre-commit critical path) and `--audit` (full-corpus scan) modes, `--json` output, `--self-test` with inline fixtures (positive + negative). Exit 0 on clean, 1 on violations, 2 on configuration error.

**Wire into `.githooks/pre-commit`** alongside the existing `cortex-check-contract --staged` and `cortex-check-prescriptive-prose --staged` calls.

## Open Questions

1. **Lint rule's interaction with `cortex_command/_interactive_overnight_check.sh:28-31,48`** — this sidecar uses `python3 -c "import json,sys; ..."` with stdlib-only imports. Under the proposed regex (`import cortex_command|from cortex_command`), these would NOT match. **Answer**: no action needed; the regex correctly scopes to `cortex_command`-imports only. Document in the Spec's negative-case tests to prevent regression.

2. **Whether to also flag `python3 -m cortex_command.<module>` invocations in skill prose** — these work under `uv tool install` because the tool's venv has `cortex_command` importable, but they don't follow the "always use console-scripts" convention the precedent lifecycle established. **Deferred: to be resolved in Spec by asking the user.** Rationale: this is a scope expansion beyond the ticket's stated intent (which explicitly names bare-Python `import cortex_command` patterns). The user may prefer to ship the narrower rule first and address `-m` callsites in a follow-up if/when an actual regression motivates it. Recommend asking explicitly.

3. **Whether to add a `--check` flag to `cortex-worktree-create` itself for the gate to use** (vs. relying on `command -v` alone) — the research recommends `command -v` only, on latency grounds (50x faster). But this leaves a residual false-positive class where the wrapper is on PATH but the wrapped function would crash (e.g., a partially-corrupt venv). **Answer**: accept the residual risk per the archived graceful-degrade spec's precedent — `cortex_command` partially installed is "treated as the user's broken install, not the skill's responsibility to mask." No `--check` flag. Document as accepted edge case in the Spec.

4. **Whether to drop the existing telemetry-style "structural marker" prose at `implement.md:22`** — that prose self-documents the `cortex-lifecycle-branch-mode` CLI invocation as the parity-test anchor. The new gate probe (`command -v cortex-worktree-create`) is an additional structural marker for the parity test in `tests/test_implement_worktree_interactive_contract.py`. **Answer**: extend the existing test rather than add a new one. Add a new assertion to `test_implement_worktree_interactive_contract.py` that the §1 region contains the substring `command -v cortex-worktree-create`. This anchors the gate against drift.

5. **Whether to emit a `worktree_gate_failed` event when the fail-open path fires** — current spec (archived) explicitly says "No telemetry. No `runtime_probe` event, no metrics, no log line per probe (only the fail-open diagnostic)." **Answer**: preserve the existing no-telemetry stance. The diagnostic prose remains the only user-facing signal on the fail-open path. Document as preserving the precedent.

6. **Whether to retire `cortex-worktree-resolve` once `cortex-worktree-create` ships** — both wrap `cortex_command.pipeline.worktree.*` functions. **Deferred: to be resolved in Spec by asking the user.** Rationale: `cortex-worktree-resolve` is consumed by `claude/hooks/cortex-worktree-create.sh` and §1a step iv's pre-flight check; retiring it requires a separate sweep. Not in scope of this lifecycle.

## Files and patterns analyzed

**Source files:**
- `/Users/charlie.hall/Workspaces/cortex-command/skills/lifecycle/references/implement.md` (§1 lines 55-66, §1a lines 123-128, full file 334 lines)
- `/Users/charlie.hall/Workspaces/cortex-command/cortex/backlog/266-gate-worktree-option-on-console-script-reachability-not-bare-python-importability.md`
- `/Users/charlie.hall/Workspaces/cortex-command/cortex/lifecycle/archive/lifecycle-skill-gracefully-degrades-autonomous-worktree-option-when-runner-absent/spec.md` (full file, 143 lines)
- `/Users/charlie.hall/Workspaces/cortex-command/cortex/lifecycle/convert-bin-cortex-and-skill-embedded/spec.md` (full file, 143 lines)
- `/Users/charlie.hall/Workspaces/cortex-command/pyproject.toml` (lines 21-63 `[project.scripts]`)
- `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/pipeline/worktree.py` (lines 170-249 `create_worktree`, full file 625 lines)
- `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/pipeline/worktree_resolve_cli.py` (full file, 53 lines — template for new wrapper)
- `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/lint/contract.py` (full file, 1669 lines — lint module template, fence state machine, sentinel pattern)
- `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/lint/prescriptive_prose.py` (full file, 411 lines — section-scoped lint precedent)
- `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/cli.py` (lines 1-80, subcommand-group precedent)
- `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/parity_check.py` (lines 430-491 — `command -v` regex precedent in parity)
- `/Users/charlie.hall/Workspaces/cortex-command/skills/lifecycle/references/_interactive_overnight_check.sh` (full file, 58 lines — stdlib-only python3 -c negative case)
- `/Users/charlie.hall/Workspaces/cortex-command/skills/lifecycle/references/complete.md:212-218` (`command -v cortex-update-item` skill-prose precedent)
- `/Users/charlie.hall/Workspaces/cortex-command/tests/test_implement_worktree_interactive_contract.py` (full file, 68 lines — structural-marker test pattern)
- `/Users/charlie.hall/Workspaces/cortex-command/bin/cortex-complexity-escalator`, `bin/cortex-check-contract`, `bin/cortex-check-parity`, `bin/cortex-jcc`, `bin/cortex-auto-bump-version` (lines 9-13 in each — `command -v cortex-log-invocation` pattern, ~15 bin/ scripts use this idiom)
- `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/auth/bootstrap.py:49`, `cortex_command/doctor/path_self_test.py:198`, `cortex_command/overnight/scheduler/macos.py:888` (`shutil.which` Python-side pattern)

**Web sources:**
- [Bash Hackers Wiki — Portability talk](https://wiki.bash-hackers.org/scripting/nonportable) — `command -v` is POSIX; `which` is not.
- [Hynek Schlawack — TIL: which is not POSIX](https://hynek.me/til/which-not-posix/) — concrete recommendation to prefer `command -v` over `which`.
- [Hacker News — 'command -v' is POSIX!!](https://news.ycombinator.com/item?id=29027095) — community confirmation of the POSIX-builtin status.

**Search patterns used:**
- `grep -rn "from cortex_command\|import cortex_command\b" skills/` → exactly one bare-python import in skills (the §1a:126 case).
- `grep -rn "python3 -c\|python3 -m\|python3 <<\|python3 - <<" skills/` → enumerated all python3 callsites in skills (most are stdlib-only).
- `grep -rn "shutil.which\|command -v" cortex_command/ skills/ bin/ hooks/` → mapped existing PATH-reachability idioms across the codebase (~30 callsites, all `command -v` or `shutil.which`).
- `grep -n "create_worktree" cortex_command/pipeline/worktree.py` → confirmed `create_worktree` signature at line 170.
