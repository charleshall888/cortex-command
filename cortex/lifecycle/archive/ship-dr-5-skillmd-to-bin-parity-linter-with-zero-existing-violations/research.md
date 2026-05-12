# Research: Ship DR-5 SKILL.md-to-bin parity linter with zero existing violations

## Epic Reference

This ticket implements DR-5 from the broader epic [`research/extract-scripts-from-agent-tool-sequences/research.md`](../../research/extract-scripts-from-agent-tool-sequences/research.md), which inventoried script-extraction candidates and identified three failure modes for SKILL.md ↔ `bin/` parity. The epic covers tickets 102–113; this lifecycle is scoped to 102 only — the static parity linter (DR-5) and same-ticket retrofit so the first run is green. Runtime adoption telemetry (DR-7, ticket 113) and the 105–111 extraction tickets are out of scope.

## Codebase Analysis

### Current `bin/` roster

| Script | Prefix | Wiring health | Notes |
|---|---|---|---|
| `bin/cortex-archive-rewrite-paths` | cortex- | Wired via `justfile:280` (recipe `lifecycle-archive`) | No SKILL.md ref; direct path reference in justfile is sufficient |
| `bin/cortex-archive-sample-select` | cortex- | Mentioned only in `README.md:96` (inventory table) | **Borderline** — no instructional doc explains when to use it |
| `bin/cortex-audit-doc` | cortex- | Wired via `README.md:96`, `docs/setup.md:216,236,354` | Standalone Anthropic-API doc auditor; periodic maintainer use |
| `bin/cortex-count-tokens` | cortex- | Wired via `README.md:96`, `docs/setup.md:216,236,354` | Token-budget audits |
| `bin/cortex-create-backlog-item` | cortex- | Wired via `skills/backlog/SKILL.md:53` | Python-shim pattern |
| `bin/cortex-generate-backlog-index` | cortex- | Wired via 6 SKILL.md sites + `CLAUDE.md:49` | Multiple defense-in-depth fallback chains |
| `bin/cortex-git-sync-rebase` | cortex- | **Drift** — 7 stale references use bare `git-sync-rebase.sh` | See retrofit list below |
| `bin/cortex-jcc` | cortex- | Wired via `CLAUDE.md:49` | |
| `bin/cortex-update-item` | cortex- | Heavily wired (10+ SKILL.md sites + `CLAUDE.md:49`) | Python-shim pattern |
| `bin/overnight-schedule` | un-prefixed | Wired via `skills/overnight/SKILL.md:234,237,318` | Out of scope for 102 — separate rename ticket |
| `bin/validate-spec` | un-prefixed | No in-scope refs (justfile recipe wraps it) | **Renamed to `bin/cortex-validate-spec` in this ticket** |

### Files that will change

**New:**
- `bin/cortex-check-parity` — the linter (Python, stdlib-only).
- `bin/.parity-exceptions.md` — allowlist (markdown table; schema TBD per Open Question 1).
- `tests/test_check_parity.py` — pytest fixtures (`tests/fixtures/parity/{valid-*, invalid-*}/`).

**Renamed:**
- `bin/validate-spec` → `bin/cortex-validate-spec`. Update `justfile:331` accordingly. Renamed file picks up `--include='cortex-*'` mirror automatically.

**Retrofitted (so first run is green — see §Adversarial F1–F5 for revised counts):**
- `skills/morning-review/references/walkthrough.md` — 5 occurrences of bare `git-sync-rebase.sh` → `cortex-git-sync-rebase` (lines 564, 610, 611, 612, 614).
- `skills/lifecycle/references/complete.md` — **4 occurrences** of `~/.local/bin/generate-backlog-index` (lines 43, 44, 67, 68). The fallback chain pattern is intentional defense-in-depth and must survive — the retrofit drops only the dead `~/.local/bin/` path, retaining the canonical `cortex-generate-backlog-index` entry.
- `skills/dev/SKILL.md:137` — **prose rewrite required**, not just path swap. Current text contains "do NOT use `uv run`, `python`, or any interpreter prefix" — a stale invocation contract.
- `skills/evolve/SKILL.md:54` — `bin/git-sync-rebase.sh` → `bin/cortex-git-sync-rebase`.
- `requirements/pipeline.md:148` — `bin/git-sync-rebase.sh` → `bin/cortex-git-sync-rebase`; drop `~/.local/bin/` deployment note.
- `tests/test_git_sync_rebase.py` — test references `bin/git-sync-rebase.sh` (which doesn't exist). Test name itself encodes the drift. Renaming the test file may be a follow-up; updating the body refs is in scope here.

**Modified for integration:**
- `justfile` — add `check-parity *args` recipe after `validate-spec` (around line 332).
- `.githooks/pre-commit` — insert Phase 1.5 between Phase 1 (plugin classification) and Phase 2 (staged-files decision). Trigger gate: `^(skills/|bin/cortex-|justfile$|bin/\.parity-exceptions\.md$|CLAUDE\.md$|requirements/|tests/)`.

### Relevant existing patterns

- **Linter template**: `scripts/verify-skill-namespace.py` — stdlib-only, `INCLUDE_GLOBS` for path scoping, `Match`/`Violation` frozen dataclasses, `--report`/`--self-test`/`--carve-out-file` flags, exit codes 0/1/2, `file:line:col: <text>` output. **Caveat (per §Adversarial A2)**: the structural skeleton transfers; the classification logic does not. verify-skill-namespace classifies against a finite set of skill names; the parity linter classifies against a filesystem state and an in-prose token space. The classification function is fundamentally different.
- **Allowlist precedents in repo**: `scripts/verify-skill-namespace.carve-outs.txt` (plain text `<file>:<line> <quoted-string>`) and `cortex_command/overnight/sync-allowlist.conf` (glob patterns). Neither has a structured rationale field — the proposed `bin/.parity-exceptions.md` table format is novel for this repo.
- **Test convention**: pytest with `tests/fixtures/{topic}/{valid-*, invalid-*}/` directory pattern, parametrized via `tests/test_skill_contracts.py`. Wired into `just test` (no separate recipe needed).
- **Hook integration**: `.githooks/pre-commit` four-phase model. Phase-2 staged-files signature is reusable: `^(skills/|bin/cortex-|hooks/cortex-validate-commit\.sh$)`.

### Integration points and dependencies

- Pre-commit hook insertion runs **before** Phase 3 (`just build-plugin`) so failures fast-fail without paying the build cost.
- `.parity-exceptions.md` itself must trigger the hook (changes to the allowlist re-run the linter to confirm no regressions).
- Build-plugin `--include='cortex-*'` glob (`justfile:501`) is the structural prefix filter. Renamed `cortex-validate-spec` newly enters the mirror; the next `build-plugin` regenerates `plugins/cortex-interactive/bin/cortex-validate-spec`. Pre-commit drift detection (Phase 4) catches if regeneration is forgotten.

### Conventions to follow

- **Naming**: `bin/cortex-check-parity` (kebab-case, no extension).
- **Shebang**: `#!/usr/bin/env python3` (stdlib-only — no `uv run --script`).
- **Permissions**: `chmod +x` (CLAUDE.md mandate).
- **Exit codes**: 0 clean, 1 violations found, 2 internal/usage error.
- **Output**: `file:line:col: <code> <text>` plain text (flake8-style), optional `--json` flag.
- **Self-test**: `--self-test` flag with positive + negative in-process fixtures.
- **Stdlib only**: no third-party deps (caveat: see §Adversarial A1 + Open Question 2).

## Web Research

### Prior art

- **Cross-reference / orphan detectors**: lychee (Rust, markdown link checker; `--include-verbatim` opts code spans into checking), remark-validate-links (offline reference checker), vulture/deadcode (Python set-difference dead-code pattern), Sentry's Reaper, YARD-Lint (Ruby docs completeness). All model parity as set difference: `set(declared) - set(referenced)` for orphans, `set(referenced) - set(deployed)` for drift — both reported by the same code path.
- **Markdown parsing**: lychee defaults to skipping fenced/inline code; for parity-style tooling the inversion is right (you *want* code-span and fenced mentions). Use a real parser (`markdown-it-py`) not regex, to avoid prose false positives.
- **Allowlist precedents** (.eslintignore, .semgrepignore, codespell-ignore): plaintext one-pattern-per-line with `#` comments. None has a first-class rationale field — convention only.
- **pre-commit framework**: exit 0/nonzero (`2=internal error` is convention only). For whole-tree scans use `pass_filenames: false` + `always_run: true`; `language: system` for custom scripts.
- **Python entry-point manifest**: `[project.scripts]` in `pyproject.toml` is the standard module → script-name bridge for "hidden via abstraction" detection.

### Anti-patterns and war stories

- **Bitcoin Core PR #16961**: Python dead-code linter removed because "the exceptions list … needs to be maintained as part of the repository." **The canonical war story for parity allowlist rot.** Lesson: every entry on the allowlist is technical debt; design the linter so the natural state is zero allowlisted entries; treat additions as code-review-worthy (require rationale, date, ticket ID).
- Regex-based bare-word reference detection consistently produces false positives in prose contexts.
- Mixing concerns (formatting + correctness + style) in one hook causes scope creep — keep this linter narrow.
- Staged-files-only checks miss cross-tree parity invariants; use `pass_filenames: false` + `always_run: true` so the hook reads the full filesystem state.

### Implementation hints

1. Three-set computation: `deployed = {bin/cortex-* executables}`; `referenced_direct = {tokens in code spans matching cortex-*}`; `referenced_indirect = {pyproject [project.scripts] + python -m mentions resolved}`. Failure modes are dual diffs.
2. Use `pyproject.toml` `[project.scripts]` as canonical bridge if/when the project adopts script entry-points.
3. Default-fail on ambiguity; resist building "maybe it's prose" heuristics — project policy is "filenames live in code spans."
4. Allowlist file must be designed against rot: rationale + date + ticket required; closed-enum category column.

## Requirements & Constraints

### Relevant requirements

- **`CLAUDE.md:18`**: "`bin/` — Global CLI utilities; canonical source mirrored into the `cortex-interactive` plugin's `bin/` via dual-source enforcement." Top-level `bin/` is canonical edit target.
- **`CLAUDE.md:47`**: "New global utilities ship via the `cortex-interactive` plugin's `bin/` directory."
- **`CLAUDE.md:48`**: "Run `just setup-githooks` after clone to enable the dual-source drift pre-commit hook."
- **`requirements/project.md:19`**: "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."
- **`requirements/project.md:21`**: "Quality bar: tests pass and the feature works as specced."
- **`requirements/project.md:31`**: "Maintainability through simplicity. The system should remain navigable by Claude even as it grows."
- **`justfile:457`**: `BUILD_OUTPUT_PLUGINS := "cortex-interactive cortex-overnight-integration"` — canonical list.
- **`justfile:501`**: `--include='cortex-*' --exclude='*'` — structural prefix glob.

### Architectural constraints

- File-based state, no server (`project.md:25`) — the linter is a static script.
- Top-level `bin/`, `skills/`, `hooks/` are canonical; `plugins/cortex-interactive/{skills,hooks,bin}/` and `plugins/cortex-overnight-integration/{skills,hooks}/` are auto-generated mirrors. Drift detection lives in `.githooks/pre-commit` Phase 4.
- The `cortex-` prefix is structural in the build glob (operationally, not requirementally — see Open Question 5).

### Constraint gaps relevant to this topic

- **No requirement governs**: pre-commit hook latency budget, false-positive tolerance, `--no-verify` bypass policy, allowlist file format, or allowlist edit-authority.
- **No quality attribute** explicitly names "discoverability" or "skill ↔ tooling reference hygiene." Closest analog: `project.md:31` "navigability."
- **Overnight commit-hook bypass** is not addressed in any requirements doc. `--dangerously-skip-permissions` (overnight default) is documented; `--no-verify` is not. Per §Adversarial S3, the overnight runner doesn't directly invoke `git commit --no-verify`, but agents inside long sessions could emit it. Out of scope for this ticket; flagged as observability gap.
- **Tests are not mandated** by requirements, but the `tests/` tree shows pytest convention and `project.md:21` ("tests pass") implies it.

## Tradeoffs & Alternatives

### Decision 1: Implementation language and shape

**Recommended: Python single-file executable, stdlib-only** (matches `bin/validate-spec` precedent).
- Reject module-shim pattern: cross-repo distribution isn't needed (the linter audits this repo only).
- Reject bash + grep: the analytical reasoning (set differences, allowlist parsing, drift vs orphan classification) is too much for shell.
- Reject ripgrep wrapper: introduces external dependency for marginal speed gain on a sub-second scan.

### Decision 2: Output reporting style

**Recommended: Plain text default `path:line:col: <code> <text>` (flake8-style), `--json` opt-in flag.**
- Default text matches `validate-spec` and `.githooks/pre-commit` conventions.
- `--json` future-proofs for CI/dashboard consumers without bloating default UX.

### Decision 3: Allowlist file format

**Recommended: Markdown table in `bin/.parity-exceptions.md` with structured columns.** Schema (per §Adversarial S1 mitigation):

| Column | Required | Closed enum | Notes |
|---|---|---|---|
| `script` | yes | (matches `bin/cortex-*`) | |
| `category` | yes | yes — see Open Question 1 | E.g. `maintainer-only-tool`, `library-internal`, `deprecated-pending-removal` |
| `rationale` | yes | no | Free-text; non-empty enforced |
| `lifecycle_id` | yes | no | Backlog/lifecycle slug or ID |
| `added_date` | yes | no | ISO date YYYY-MM-DD |

The linter validates each row at load time; any row failing validation produces a violation against the allowlist file itself (`bin/.parity-exceptions.md:LN:1: E001 invalid allowlist entry`). Reject inline-comment formats (defeat centralized audit) and YAML/TOML (break the .md convention pinned by the ticket).

### Decision 4: Pre-commit hook trigger scope

**Recommended: Staged-files conditional with `--diff-filter=ACMRD`, plus full-tree `just check-parity` for manual.**
- The `D` (delete) filter is critical — handles renames/deletions that would otherwise miss orphan introduction.
- Trigger signature: `^(skills/|bin/cortex-|justfile$|bin/\.parity-exceptions\.md$|CLAUDE\.md$|requirements/|tests/)`.

### Decision 5: Indirect-invocation detection

**Recommended: SKIP justfile parsing entirely** (web agent's recommendation wins on empirical grounds — see §Adversarial F7). The justfile recipes that look like they wrap `bin/cortex-*` actually parallel-implement via `python3 backlog/X.py`; the only true direct-bin reference (`validate-spec`) is caught by literal path matching alone.

For Python-module-shim recognition (`cortex-update-item` etc.), use the allowlist's `category` column or rely on the SKILL.md sites already directly referencing the canonical script name.

### Decision 6: Justfile recipe shape

**Recommended: `just check-parity *args`** (single recipe, args passthrough — matches `validate-spec *args` pattern). The Python script handles `--staged`, `--strict`, `--lenient`, `--json`, `--self-test` internally.

### Decision 7: Drift-vs-orphan reporting and polarity

**Recommended (revised per §Adversarial S4): both default to exit 1; `--lenient` opts into "orphan = warning, exit 0."**
- Drift (referenced-not-deployed): always exit 1. Real bug.
- Orphan (deployed-not-referenced): default exit 1, `--lenient` flag drops to warning.
- Polarity flip from the original tradeoffs recommendation. Rationale: defaulting orphan to exit 0 (the original recommendation) means no commit ever fails on orphans, the allowlist never gets pruned, and the linter doesn't pressure anyone to wire scripts. The Bitcoin Core failure mode. Default strict; opt-in lenient with explicit user intent.

### Cross-cutting recommendations

- Lean on `validate-spec` for shape; do not copy `verify-skill-namespace.py` classification logic — the problem is structurally different.
- Treat `bin/.parity-exceptions.md` as a living architectural changelog. Every entry is a small ADR.
- Resist scope creep on indirect-invocation detection. If module-shim count grows past ~5, revisit; not today.

## Adversarial Review

### Failure modes

**F1 — naive regex false positives.** A `\bcortex-[a-z][a-z0-9-]*\b` pattern matches 11+ tokens that look like bin scripts but aren't: `cortex-cleanup-session`, `cortex-scan-lifecycle`, `cortex-validate-commit`, `cortex-worktree-create`, `cortex-worktree-remove`, `cortex-tool-failure-tracker`, `cortex-permission-audit-log`, `cortex-skill-edit-advisor`, `cortex-output-filter`, `cortex-notify`, `cortex-sync-permissions`. These are hook scripts (in `hooks/` or `claude/hooks/`), plugin names, or shim labels. **Mitigation**: narrow trigger pattern to (a) inside backtick code spans / fenced code blocks only, and/or (b) require a path prefix (`bin/cortex-` / `cortex-` followed by shell-context syntax). See Open Question 2.

**F2 — `git-sync-rebase` retrofit scope larger than reported.** Plus auto-mirror sites that build-plugin will repair, plus `tests/test_git_sync_rebase.py` (test file name itself encodes drift).

**F3 — `complete.md` undercounted**: 4 occurrences (43, 44, 67, 68), not 2. Defense-in-depth fallback chain pattern must survive — retrofit drops only the dead `~/.local/bin/` path while retaining canonical cortex-generate-backlog-index.

**F4 — `dev/SKILL.md:137` requires prose rewrite**, not just path swap. The surrounding sentence contains stale invocation contract ("do NOT use `uv run`, `python`, or any interpreter prefix"). Repointing path is insufficient.

**F5 — `tests/` scope decision unaddressed.** verify-skill-namespace.py precedent includes `tests/**/*.py`. If the parity linter follows, `tests/test_git_sync_rebase.py` enters retrofit. Recommended: include `tests/` in scope.

**F7 — justfile-parsing premise is empirically false.** Of 5 enumerated recipes, only `validate-spec` directly invokes a `bin/` script (`python3 bin/validate-spec` — caught by literal path matching). The others (`backlog-index`, `backlog-close`, `validate-commit`, `lifecycle-archive`) call sibling scripts under `backlog/`, `hooks/`, or `bin/` paths that don't need transitive resolution. **Skip the parser.**

**F8 — phase ordering hazard**: the linter must scan canonical paths only (`skills/`, `CLAUDE.md`, `README.md`, `docs/`, `requirements/`, `hooks/`, `tests/`). Excluding `plugins/*/` prevents double-counting and avoids ordering races with `build-plugin`.

**F9 — proposed day-one allowlist misclassifies wired scripts.**
- `cortex-audit-doc`, `cortex-count-tokens`: wired via `README.md:96` + `docs/setup.md:216,236,354`.
- `cortex-archive-rewrite-paths`: wired via `justfile:280` (direct bin/ path).
- `cortex-archive-sample-select`: only enumerated in `README.md:96` — borderline.

Allowlisting these would mark wired scripts as "exempt from wiring requirements" — exactly the rot pattern. **Day-one allowlist size should be 0 or 1, not 4.** See Open Question 3.

### Security concerns / anti-patterns

**S1 — allowlist rationale is decorative without enforcement.** Mitigation captured in Decision 3 schema (closed-enum category, ISO date, lifecycle ID, fail-closed validation).

**S2 — README-as-wiring is a fragile contract.** A flat enumeration table at `README.md:96` lists 9 scripts — by lazy "any token mention" rules, the README alone would wire every tool, hiding genuine orphans. **Mitigation**: classify the README inventory as documentation-only; require a SKILL.md or `docs/*.md` body section beyond a flat enumeration. See Open Question 4.

**S3 — `--no-verify` and overnight-runner bypass.** The overnight runner doesn't directly invoke `git commit --no-verify` (verified in `cortex_command/overnight/runner.py`), but agents in long sessions can emit it. There is no observability hook recording such bypasses. **Out of scope for this ticket** — flagged as separate observability gap, document in linter's SKILL.md so the next reader doesn't assume the linter is enforceable post-commit.

**S4 — exit-code polarity (already addressed in Decision 7)**: orphan defaults to exit 1; `--lenient` opts in. Allowlist is the relief valve.

### Assumptions to verify before commit

**A1 — stdlib-only Python may not be enough.** The token space `cortex-foo` is ambiguous in prose (unlike `/cortex:foo` which is unambiguous in any context). May require AST-aware code-span detection. Resolution path: write three regex variants (naive, code-fence-aware, AST-aware), count false positives on actual repo, decide. See Open Question 2.

**A2 — verify-skill-namespace.py classification doesn't transfer cleanly.** Structural skeleton (CLI, exit codes, carve-outs, self-test) does. Classification function is fundamentally different (open filesystem state vs closed skill name set). Don't underestimate the rewrite cost.

**A3 — justfile-recipes-wrap-bin transitively was untested.** Resolved as false in F7.

**A4 — "first-run green" is harder than originally proposed.** Given F1 + F3 + F4 + F5, retrofit surface is 3-4× larger than tradeoffs agent reported. **Resolution path**: dry-run the proposed regex against HEAD before declaring scope. See Open Question 6.

**A5 — `markdown-it-py` PyPI dep may be cheaper than regex juggling.** If naive regex produces >5 false positives, the dep cost is outweighed by maintainability. Don't pre-decide.

### Recommended mitigations (incorporated above except where noted)

1. Run a dry-run of the proposed pattern against HEAD before final scope. **Pending — Open Question 6.**
2. Day-one allowlist: 0 or 1 entry. **Captured in Decision 3 / F9.**
3. Skip justfile parser. **Captured in Decision 5.**
4. Exclude `plugins/*/` from scan walk. **Captured in F8 / Decision 4 trigger signature.**
5. Include `tests/` in scope. **Captured in F5 / Decision 4 trigger signature.**
6. Default strict, opt-in lenient. **Captured in Decision 7.**
7. Allowlist row schema with closed-enum category + ISO date + lifecycle ID. **Captured in Decision 3.**
8. `--list-orphans` / `--list-drift` separation in output. **Spec-level decision; see Open Question 7.**
9. Don't audit `--no-verify` in this ticket. **Documented in S3.**
10. Fix `dev/SKILL.md:137` prose before shipping linter. **Captured in retrofit list.**

## Open Questions

1. **Allowlist `category` enum.** Closed set TBD. Initial proposal: `maintainer-only-tool`, `library-internal`, `deprecated-pending-removal`, `experimental`. Spec phase to finalize. Determines whether the day-one allowlist needs zero or one entry (see Q3).

2. **Markdown parser dep choice.** Stdlib regex (narrow patterns: token-in-code-span only) vs `markdown-it-py` (AST-aware, adds PyPI dep). Resolution: empirical dry-run during Spec or early Implement — count false positives on HEAD with each candidate. Defer commitment until count is in hand.

3. **Day-one allowlist contents.** Per §F9, the 4-entry allowlist proposed during research is wrong: 3 of 4 scripts are already wired (README + setup.md + justfile). Day-one allowlist is most likely empty or a single entry for `cortex-archive-sample-select` (which only appears in the README inventory table). Spec decision: require this ticket to either wire `cortex-archive-sample-select` into a doc body section OR allowlist with `category: maintainer-only-tool`.

4. **README-as-wiring contract.** Does an entry in `README.md:96` flat-enumeration table count as a SKILL.md "reference" for parity purposes, or must wiring come from a SKILL.md / `docs/*.md` body section? Recommendation: README enumeration alone does NOT satisfy parity (S2 mitigation). Spec phase to decide.

5. **`cortex-` prefix as policy-or-requirement.** Currently structural in build glob, not stated as a project requirement. The renamed `bin/cortex-validate-spec` (this ticket) and the deferred `bin/overnight-schedule` rename (separate ticket) imply the convention is policy. Should the linter itself flag any new top-level `bin/` script that lacks the `cortex-` prefix as a violation? Recommendation: yes, as a separate violation class `E002 missing cortex- prefix`. Out of scope for first ship; document as future enhancement.

6. **Empirical first-run-green verification.** Before the linter ships, dry-run the chosen regex/parser against current HEAD and report all violations. The retrofit list in this research must absorb every violation surfaced by the dry-run. If dry-run discovers more than ~10 unexpected violations, scope expands and the spec must reconcile.

7. **Output report structure.** Single combined section vs separate `--list-drift` / `--list-orphans` / `--list-allowlist-violations` outputs. Recommendation: default combined report; separation flags as opt-in. Spec to confirm.

8. **`tests/` scope inclusion.** Recommended yes (matches verify-skill-namespace.py precedent and surfaces `tests/test_git_sync_rebase.py` drift). Adds one retrofit class. Spec to confirm.

9. **Allowlist file location.** `bin/.parity-exceptions.md` matches ticket spec but the dotfile-in-bin pattern is novel. Alternatives: `bin/parity-exceptions.md` (no dot) or `.parity-exceptions.md` (repo root). Recommendation: keep `bin/.parity-exceptions.md` per ticket — colocated with the scripts it governs, dot-prefix signals "config not script" to readers.

10. **Pre-commit hook insertion ordering.** Phase 1.5 (between Phase 1 plugin-classification and Phase 2 staged-files) recommended in research but ordering details belong in spec. Phase 3 (`build-plugin`) MUST run after parity check so failures fast-fail without paying the build cost.
