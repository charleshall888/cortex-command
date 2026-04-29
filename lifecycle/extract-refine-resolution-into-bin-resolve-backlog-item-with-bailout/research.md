# Research: Extract /refine resolution into bin/cortex-resolve-backlog-item with bailout

> Backlog item: 109. Discovery context: `research/extract-scripts-from-agent-tool-sequences/research.md` (C5).
> Clarified intent: extract `/refine` Step 1 fuzzy-input resolution into a new `bin/cortex-resolve-backlog-item` that returns structured JSON on unambiguous matches and exits non-zero on ambiguity/no-match — agent skips deterministic tool calls on the happy path while preserving today's inline disambiguation flow on the unhappy path.

## Codebase Analysis

### Today's `/refine` Step 1

- `skills/refine/SKILL.md:22-35` and `plugins/cortex-interactive/skills/refine/references/clarify.md` §1 (L7-23) define the flow as **agent-side prose** — the agent makes ad-hoc Glob/Grep/Read calls against `backlog/[0-9]*-*.md` and applies the input-classification protocol manually. There is no resolver script today. The protocol records three load-bearing fields:
  - `backlog-filename-slug` (e.g., `109-extract-...`)
  - `item-title` (frontmatter `title:`)
  - `lifecycle-slug` (derived via canonical `slugify()` rules — currently the agent applies them by reading the prose at `skills/refine/SKILL.md:31`)
- The plugin mirror at `plugins/cortex-interactive/skills/refine/...` is rsync-rebuilt by `just build-plugin`.

### Canonical `slugify()`

- `cortex_command/common.py:59-81`:
  ```python
  def slugify(title: str) -> str:
      slug = title.lower()
      slug = re.sub(r"[_/]", " ", slug)
      slug = re.sub(r"[^a-z0-9\s-]", "", slug)
      slug = re.sub(r"[\s-]+", "-", slug)
      return slug.strip("-")
  ```
- All six existing callers `from cortex_command.common import slugify` (`cortex_command/dashboard/data.py:1088`, `cortex_command/overnight/backlog.py:115`, `cortex_command/overnight/report.py:333`, `backlog/create_item.py:60,112`, `backlog/generate_index.py:112`).
- **No `bin/*` script currently calls `slugify`.**

### Existing bin/ scripts as precedent

| Script | Style | Shebang | Exit codes | JSON shape | cortex_command access |
|---|---|---|---|---|---|
| `cortex-archive-rewrite-paths` | Self-contained Python | `#!/usr/bin/env python3` | `0`/`2` (usage) | NDJSON per slug | none (sys.path injection if needed) |
| `cortex-validate-spec` | Self-contained Python | `#!/usr/bin/env python3` | `0`/`1` | none | none |
| `cortex-check-parity` | Self-contained Python | `#!/usr/bin/env python3` | `0`/`1`/`2` | optional `--json` array | none |
| `cortex-update-item` | Bash dispatcher | `#!/bin/bash` | `0`/`1`/`2` (wrapper-level) | none | tries `python3 -m cortex_command.backlog.update_item` then `$CORTEX_COMMAND_ROOT/backlog/update_item.py` |
| `cortex-create-backlog-item` | Bash dispatcher | same as update-item | same | none | same dispatcher pattern |
| `cortex-generate-backlog-index` | Bash dispatcher | same | same | none | same |
| `cortex-audit-doc` / `cortex-count-tokens` | PEP 723 inline | `#!/usr/bin/env -S uv run --script` | text | text | none |

- **Crucial finding (adversarial agent):** the bash dispatchers reference `cortex_command.backlog.update_item` and `.create_item` modules **that do not exist** today. Branch (a) is dead; branch (b) (root-level `backlog/*.py`) is the only path that works. The `cortex_command/backlog/` package is currently aspirational.
- **Mandatory shim** (`.githooks/pre-commit` Phase 1.6, enforced via `bin/cortex-invocation-report --check-shims`): every `bin/cortex-*` script must include the `cortex-log-invocation` shim line in its first 50 lines. Python form (per `bin/cortex-archive-rewrite-paths:46`):
  ```python
  import os, subprocess, sys; subprocess.run([os.path.join(os.path.dirname(os.path.abspath(__file__)), "cortex-log-invocation"), sys.argv[0], *sys.argv[1:]], check=False)
  ```

### Existing fuzzy-resolution helpers

- `backlog/update_item.py:130-169` — `_find_item(slug_or_uuid, backlog_dir) -> Path | None`. Four-tier match (exact filename → numeric `^NNN-` prefix → substring filename match → UUID prefix). **Returns the first match only** — cannot signal ambiguity. Other callers depend on this signature; do not modify in place.
- `cortex_command/overnight/backlog.py:217 _parse_frontmatter()`, `:250 parse_backlog_dir()`, `BacklogItem` dataclass with `resolve_slug()` (L100-115) implementing the `lifecycle_slug` → spec/research dirname → `slugify(title)` fallback chain.
- `parse_backlog_dir()` reads files without locks; `cortex_command/common.py:atomic_write()` (L366-407) is tempfile + `os.replace` so reads see either pre-or-post snapshot, never torn writes.

### `install_guard` blast radius (adversarial finding)

- `cortex_command/__init__.py:13-15` invokes `cortex_command.install_guard.check_in_flight_install()` on **every import of the `cortex_command` package**.
- `cortex_command/install_guard.py:184-202` — carve-outs are pytest, `CORTEX_RUNNER_CHILD=1`, dashboard, `CORTEX_ALLOW_INSTALL_DURING_RUN=1`. **An interactive `/refine` Bash invocation has none of these set.**
- Consequence: a resolver implemented as `python3 -m cortex_command.backlog.resolve` (or any path that imports `cortex_command`) will raise `InstallInFlightError` (sys.exit 1) when invoked during an active overnight session. The agent sees a non-zero exit and falls through to disambiguation prose — masking the real cause as "ambiguous match." This is a worse UX than today.

### Backlog item structure & mode-detection reality

- 148 backlog items present today. **98 of 148 lack an `id:` frontmatter field** (verified by adversarial agent). The `clarify.md` §1 protocol's "numeric input matches by `id:` frontmatter" is aspirational and inconsistently applied. The 50 items that *do* carry `id:` agree with their filename prefix (zero disagreements). Filename-prefix matching is the only correct strategy for numeric input.
- Title-phrase ambiguity: 25 titles contain "overnight," 14 "lifecycle," 10 "extract." Naive substring matching produces multi-match results frequently. `update_item.py:_find_item:156-160` does naive `in` substring and silently returns first hit.
- Currently zero pairs where one title is a substring of another, but a sequel item ("X v2") would silently shadow the original under first-match-wins.

### Dual-source / parity enforcement

- `bin/cortex-check-parity:55-90` requires every new `bin/cortex-*` script to be referenced in: `CLAUDE.md`, `claude/hooks/cortex-*.sh`, `docs/**/*.md`, `hooks/cortex-*.sh`, `justfile`, `requirements/**/*.md`, `skills/**/*.md`, `tests/**/*.py`, `tests/**/*.sh`. Plugin-tree mirrors are NOT scanned.
- `bin/.parity-exceptions.md`: closed enum (`maintainer-only-tool`, `library-internal`, `deprecated-pending-removal`); rationale ≥30 chars; forbidden literals (`internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary`).
- `justfile:483-507` uses `rsync --include='cortex-*'` so any new `bin/cortex-*` auto-mirrors to `plugins/cortex-interactive/bin/`. No manual manifest edit required.
- `.githooks/pre-commit` Phase 4 fails the commit if plugin-mirror drift is detected — author workflow: edit `bin/`, run `just build-plugin`, stage both paths in one commit.

### Test patterns

- `tests/test_archive_rewrite_paths.py` demonstrates the canonical pattern: in-process tests via `importlib.machinery.SourceFileLoader` (L37-54) for unit-testable internal functions, plus subprocess invocation for CLI/exit-code/JSON contract (L320-349).

### Sandbox / settings

- `.claude/settings.local.json:179` allows `Bash(python3 -m cortex_command.*)`. A new `Bash(cortex-resolve-backlog-item *)` allowlist row is required if the script is invoked by bare name; otherwise every `/refine` call prompts the user. This must land in the same commit.

### Files that will change

- **New** `bin/cortex-resolve-backlog-item` (top-level canonical source; auto-mirrored to `plugins/cortex-interactive/bin/`).
- **Edited** `skills/refine/SKILL.md` Step 1 (L22-35) — call the script first; fall through to today's prose on non-zero.
- **Edited** `skills/refine/references/clarify.md` §1 (L7-23) — same prose, tightened.
- **Edited** `.claude/settings.local.json` — add `Bash(cortex-resolve-backlog-item *)` allowlist row.
- **New** `tests/test_resolve_backlog_item.py`.
- **Auto-regenerated** plugin mirrors via `just build-plugin`.
- **No edit needed** to `justfile` (rsync glob covers any `cortex-*`) or `bin/.parity-exceptions.md` (script will be wired via SKILL.md).

## Web Research

### CLI exit-code conventions

- `git rev-parse` uses generic exit **128** for fatal/ambiguous; does not distinguish ambiguous vs not-found. Disambiguation lives in `--disambiguate=<prefix>` output, not exit codes. Source: https://git-scm.com/docs/git-rev-parse
- `git checkout` DWIM rule (commit `8d7b558`): auto-resolve when exactly one remote matches; otherwise refuse with exit 1. Maps directly to the design proposed here. Source: https://github.com/git/git/commit/8d7b558baebe3abbbad4973ce1e1f87a7da17f47
- `apt-get` / `dnf` / `brew` / `gh` — none use distinct exit codes for ambiguous vs not-found. `gh` documented codes are only `0`/`1`/`2`/`4` (auth required). Source: https://cli.github.com/manual/gh_help_exit-codes
- **sysexits.h** (BSD): `EX_OK=0`, `EX_USAGE=64`, `EX_DATAERR=65`, `EX_NOINPUT=66`, `EX_UNAVAILABLE=69`, `EX_SOFTWARE=70`. Widely cited but inconsistently adopted. Source: https://man.openbsd.org/sysexits.3
- Anthropic Claude Code hooks: stdout JSON parsed only on exit 0; **exit 2 specifically surfaces stderr to the model**. Source: https://code.claude.com/docs/en/hooks

### JSON output for agent consumption

- Consensus across agent-CLI guidance (dev.to, InfoQ, Slava Kurilyak): structured JSON to stdout, human messages to stderr; never mix prose into stdout JSON.
- For n=1 records (the happy path here), single JSON object on stdout is the right shape — NDJSON adds no value for unary results.
- gh CLI is repeatedly cited as a *negative* example for stdout/stderr violations.

### Fuzzy-match resolution

- `git checkout`/`git switch` DWIM is the closest published prior art for n=1-resolve, n>1-bail.

### Bailout-to-LLM design pattern

- "SLM-default LLM-fallback" (Microsoft Strathweb 2025), "Workflow-first agent design" (MindStudio), "Compound AI systems" (Praetorian/Berkeley) all describe the same shape: deterministic happy path, escalate to LLM only on low confidence. Confirms the design is industry-recognized; no canonical name.

### Python `bin/` packaging

- `[project.scripts]` entry-point (in `pyproject.toml`) is documented best practice.
- `uv tool install -e .` lacks editable support (uv issue #5436); `uv pip install -e .` or `uv sync` + `uv run` is the editable workflow.
- PEP 723 inline metadata is wrong fit for sibling-package imports (it solves third-party deps in a script, not project-internal package imports).

### Recommended exit-code values from web research

| Outcome | Exit | Stdout | Stderr |
|---|---|---|---|
| Unambiguous match | 0 | Single JSON object | (empty/quiet) |
| Ambiguous (n > 1) | 2 | (empty, or candidate JSON for agent) | Human-readable list |
| No match (n = 0) | 3 | (empty) | Human prose |
| Usage error | 64 (EX_USAGE) | (empty) | usage string |

> Adversarial caveat (resolved below): codebase agent and web agent both recommend distinct codes; adversarial agent recommends collapsing to 0/1 only. See **Open Questions §1**.

## Requirements & Constraints

- **`requirements/project.md:27` — SKILL.md-to-bin parity enforcement** (verbatim):
  > `bin/cortex-*` scripts must be wired through an in-scope SKILL.md / requirements / docs / hooks / justfile / tests reference (see `bin/cortex-check-parity` for the static gate). Drift between deployed scripts and references is a pre-commit-blocking failure mode. Allowlist exceptions live at `bin/.parity-exceptions.md` with closed-enum categories and ≥30-char rationales.
- **`requirements/project.md:25` — file-based state**: lifecycle/backlog/pipeline state is plain files. JSON output for the new script is consistent.
- **`requirements/project.md:19` — complexity must earn its place**: the bailout design is justified because it ships unconditionally with no unhappy-path regression.
- **`requirements/project.md:13` — handoff readiness**: the new script must not introduce overnight-blocking failure modes (see install_guard finding).
- **`requirements/observability.md:53-59` — cortex-log-invocation shim**: every `bin/cortex-*` must call the fail-open shim line.
- **`requirements/multi-agent.md`**: agent stderr captured + capped at 100 lines — relevant for the candidate-list output on ambiguous bail.
- **`requirements/pipeline.md`** — atomicity (tempfile + `os.replace`); read-snapshot semantics already correct in `parse_backlog_dir`.

## Tradeoffs & Alternatives

### Approach A — Self-contained Python script in `bin/` (ticket's literal proposal)

- **Description**: New `bin/cortex-resolve-backlog-item`, `#!/usr/bin/env python3`, with `sys.path` injection to import `cortex_command.common.slugify` (matches `cortex-archive-rewrite-paths` precedent). All resolution logic lives in the script file; tested via `importlib.machinery.SourceFileLoader` for unit tests + subprocess for CLI contract.
- **Pros**: smallest mental model; matches existing self-contained-Python precedent; no `cortex_command.backlog.*` package shadow; explicit control over what gets imported (can avoid full `cortex_command/__init__.py` if implemented carefully).
- **Cons**: re-implements YAML frontmatter scanning that `update_item.py` already does → drift risk; no Python-callable form for future overnight callers; subprocess-only testing is slightly less ergonomic.
- **Complexity**: S — ~80–120 line script + ≤6 unit tests + SKILL.md edit + settings allowlist row.
- **Maintenance**: moderate. Drift risk against `clarify.md` §1 prose is the dominant concern — mitigated by treating the script as single source of truth (Adversarial §12).

### Approach B — `cortex_command/backlog/resolve.py` module + thin `bin/` shim

- **Description (Tradeoffs agent's recommendation)**: Add a new `cortex_command/backlog/` package hosting `resolve.py`. `bin/` script is a 5–10 line shim using the `cortex-update-item` dispatcher pattern.
- **Pros**: testable directly via `from cortex_command.backlog.resolve import resolve`; reusable from Python callers; slots into the namespace the existing dispatcher already references (`cortex_command.backlog.update_item`).
- **Cons (adversarial pushback, validated)**:
  - **`install_guard` blast radius**: every import of `cortex_command` runs `check_in_flight_install()`. During an active overnight session, any daytime `/refine` invocation that imports `cortex_command` raises `InstallInFlightError` → sys.exit 1 → agent treats as "ambiguous" and prompts user → silent UX regression vs today.
  - `cortex_command.overnight.backlog` (existing module) and proposed `cortex_command.backlog.*` (new package) create two distinct things both named "backlog" in the same package tree — navigation hazard.
  - Materializing `cortex_command/backlog/` for a single new module activates branch (a) in the bash dispatchers asymmetrically — without also moving `update_item.py` and `create_item.py`, the codebase ends up half-migrated.
- **Complexity**: S–M (would have been S without install_guard concerns; the migration question makes it M).
- **Maintenance**: would have been lowest, but install_guard blast radius and namespace shadow flip the calculus.

### Approach A' — Adversarial agent's hybrid: implementation alongside `backlog/*.py` at repo root + self-contained `bin/` script that uses sys.path injection

- **Description**: Place `backlog/resolve.py` alongside the existing root-level `backlog/update_item.py` and `backlog/create_item.py`. The `bin/cortex-resolve-backlog-item` is self-contained Python with `sys.path` injection (no `from cortex_command import …`). Imports `slugify` either by re-implementing the small function locally, or by importing only `cortex_command.common` (which does *not* trigger `cortex_command.__init__.py`'s install_guard call — verify in spec).
- **Pros**: avoids install_guard blast radius; avoids `cortex_command/backlog/` namespace shadow; matches existing root-`backlog/` layout; module-level testable; future Python callers can `from backlog.resolve import resolve` (matching the existing root-level pattern in `backlog/update_item.py`'s sys.path hack).
- **Cons**: continues the asymmetric "half packaged, half root-level" state of the codebase (which is the real problem and out of scope for this ticket).
- **Complexity**: S — module ~80 lines + bin script ~30 lines + tests ~80 lines + SKILL.md/clarify.md edit + settings row.
- **Maintenance**: best of the realistic options. **This is the recommendation that survives the adversarial review.**

> Verification needed during implementation: importing `cortex_command.common` actually runs `cortex_command/__init__.py:13-15` (the package init runs on any submodule import). So `from cortex_command.common import slugify` *does* trigger install_guard. Mitigations: (a) re-implement the 6-line `slugify` function locally with a comment pointing at the canonical source + a test that asserts behavioral equivalence (drift test); (b) inline-extract the slugify body into a tiny helper that does not depend on the package; or (c) accept the install_guard tradeoff and document it. **Recommend (a) — drift test is cheap insurance.**

### Approach C — Extend `cortex-update-item` with `--resolve-only`

- **Description**: Add a flag to `bin/cortex-update-item` that performs resolution and exits without writing.
- **Cons**: `update_item.py:_find_item()` does NOT currently do title-phrase fuzzy match — it does exact filename, numeric prefix, substring filename, and UUID prefix only. Adding title-fuzzy match here changes the contract for write callers. Also conflates read and write failure modes.
- **Verdict**: rejected. Not pursued further.

### Approach D — Reject extraction (wontfix)

- **Pros**: zero new code, zero drift risk.
- **Cons**: foregoes the lifecycle-slug determinism win (today the agent manually applies slugify rules from prose — a known error source). Foregoes the Pareto improvement that the bailout design specifically guarantees.
- **Verdict**: rejected — extraction's value is real.

### Approach E — PreToolUse hook injects resolution into agent context

- **Verdict**: rejected. No precedent for skill-arg preprocessing hooks; fragile invocation detection; out of step with the C5 thesis (the script *is* the unit of reuse).

### Recommended approach: **A'** (root-level `backlog/resolve.py` module + self-contained `bin/` script with locally-implemented slugify)

Approach A' captures Approach B's testability and reusability without triggering `install_guard` and without introducing the `cortex_command.backlog.*` namespace shadow. The slugify-drift-test is a one-line assertion comparing local re-implementation against the canonical source (using subprocess or fixture-based comparison without a full `cortex_command` import chain) — this trades a tiny duplication for protection against the most consequential failure mode the adversarial agent surfaced.

## Adversarial Review

The full adversarial findings are integrated above (in Codebase Analysis §install_guard, Tradeoffs §Approach B Cons, and the recommendation flip from B → A'). Items not yet addressed inline:

- **Pareto-improvement claim is not unconditional**: extra Bash round-trip + Python startup + log-invocation shim is comparable to or slower than a parallel Glob+Grep+Read in-context. Honest framing: "deterministic on the happy path, falls back to today's flow on bailout." The win is correctness (`lifecycle-slug` exactness, ambiguity surfaced rather than silently picked) more than latency.
- **Bit-rot risk + DR-7 sequencing**: ticket 109's "telemetry deferred to ticket 103 post-ship" is a real risk per the discovery research's own DR-7. Without runtime adoption telemetry, this script could ship and never get invoked. Resolved as **Open Question §6** below.
- **JSON `frontmatter` field is a context-pollution risk**: the field is undefined; default-everything could drag `discovery_source`, `parent`, `blocked-by` chains into the agent's context. Recommend closed-set fields explicitly. Resolved in **Open Question §3**.
- **Concurrency**: read-snapshot semantics are already correct (`atomic_write` ensures no torn reads). Document the snapshot semantic; the resolver's frontmatter is read-once and non-authoritative.
- **Parity gate hostage**: the SKILL.md edit and `bin/` script must land in one commit. Document this in spec.
- **Sandbox**: add `Bash(cortex-resolve-backlog-item *)` to `.claude/settings.local.json` allowlist in the same commit.
- **Prose drift**: make the resolver script the single source of truth for matching rules; reduce `clarify.md` §1 to "run script; on non-zero, present candidates from stderr."

## Open Questions

These survived the agents' synthesis and need user resolution at Spec phase or earlier:

### §1 — Exit-code contract: 4 codes (0/2/3/64) vs 2 codes (0/1)

**Codebase agent + Web agent recommend** distinct codes (0 unambiguous / 2 ambiguous / 3 no-match / 64 usage). **Adversarial agent recommends** collapsing to 0/1 — argument: SKILL.md prose branching on multiple non-zero codes is fragile, and the script's whole job is "did I succeed deterministically?" — anything else is a fallback that doesn't need typed taxonomy. The ticket explicitly says "Non-zero distinct codes for: ambiguous, no-match" which leans 4-code, but doesn't mandate it.

**Deferred:** will be resolved in Spec by asking the user — this is a value-vs-simplicity preference call. Spec will surface both options with concrete SKILL.md branching prose for each.

### §2 — JSON output schema (resolve naming drift)

The ticket's Context section names three slugs (`backlog-filename-slug`, `item-title`, `lifecycle-slug`); the Scope section names five JSON keys (`{filename, slug, title, lifecycle_slug, frontmatter}`). The two do not align by name.

**Resolved** (research-driven proposal, to be confirmed in Spec):
```json
{
  "filename": "109-extract-refine-resolution-into-bin-resolve-backlog-item-with-bailout.md",
  "backlog_filename_slug": "109-extract-refine-resolution-into-bin-resolve-backlog-item-with-bailout",
  "title": "Extract /refine resolution into bin/resolve-backlog-item with bailout",
  "lifecycle_slug": "extract-refine-resolution-into-bin-resolve-backlog-item-with-bailout",
  "frontmatter": { /* see §3 */ }
}
```
Names use snake_case to match Python conventions and the `BacklogItem` dataclass field names.

### §3 — `frontmatter` field shape (closed-set vs full)

**Adversarial finding**: returning the full frontmatter drags fields like `discovery_source`, `parent`, `blocked-by` chains into the agent's context. Backlog body text is excluded by the schema regardless.

**Deferred:** will be resolved in Spec by asking the user — closed-set proposal: `{id, title, status, complexity, criticality, lifecycle_slug, lifecycle_phase, spec, parent}`. Open question for user: any additional fields downstream `/refine` phases need (e.g., `tags`, `priority`, `discovery_source`)?

### §4 — Disambiguation rules (when to bail vs commit)

**Resolved** (research-driven, mirrors `git checkout` DWIM):
- Numeric input (e.g., `109`): exact `^NNN-` filename-prefix match. n=1 → resolve. n>1 → impossible (filenames unique) but defensive: bail. n=0 → bail.
- Kebab input (e.g., `extract-refine-resolution`): exact filename slug match (after stripping `NNN-` prefix and `.md`). Multiple matches are impossible by construction (filenames unique). Bail on n=0.
- Title-phrase input: case-insensitive substring match against `title:` frontmatter, OR `slugify()`-normalized substring match against the slugified title. n=1 → resolve. n>1 → bail with candidate list. n=0 → bail.

**Reject `id:` frontmatter matching**: 98 of 148 backlog items lack the field; filename-prefix is the only correct strategy.

### §5 — Should the script emit candidate hints across the bail boundary?

**Adversarial recommendation**: yes — emit candidates as human-readable prose on stderr only (never via stdout JSON, to keep the exit-0-implies-stdout-JSON contract clean). The agent's Bash tool surfaces stderr; the SKILL.md fallback can present candidates directly without re-scanning.

**Resolved** (research-driven proposal, to be confirmed in Spec): on bail, write up to N (e.g., 5) candidate `{filename, title}` pairs to stderr in human-readable form. SKILL.md prose: "If the script exits non-zero, present the candidate list from stderr to the user and ask them to choose."

### §6 — Should ticket 103 (DR-7 runtime telemetry) pre-sequence ticket 109?

**Adversarial concern**: without runtime adoption telemetry, this script can ship and never be invoked (3 of 5 prior scripts hit this failure mode). The ticket marks 103 as "post-ship deferred."

**Deferred:** will be resolved in Spec by asking the user — strict-blocking dependency vs ship-and-trust-static-parity. The user has already weighted this in 109's "out of scope" framing; we'll surface this for explicit confirmation.

### §7 — Slugify dependency strategy

**Resolved** (research-driven, integrated into Approach A' recommendation): re-implement the 6-line `slugify` function locally inside the script (or alongside in `backlog/resolve.py`) with a comment citing the canonical source. Add a drift-detection test that asserts behavioral equivalence against `cortex_command.common.slugify` over a fixture set (e.g., 20 input/expected pairs). Avoids `cortex_command/__init__.py:install_guard` blast radius. Tradeoff: small duplication for blast-radius isolation; test catches drift.

### §8 — Single-commit landing requirement

**Resolved** (research-driven): the `bin/` script, plugin mirror, SKILL.md/clarify.md edits, `.claude/settings.local.json` allowlist row, and `tests/test_resolve_backlog_item.py` must all land in one commit. The pre-commit parity gate forces this.

### §9 — `clarify.md` §1 prose simplification after the script ships

**Adversarial recommendation**: after the script lands, prune `clarify.md` §1 to the single instruction "Run `cortex-resolve-backlog-item <input>`. On exit 0, parse the JSON. On non-zero, present candidates from stderr and ask the user to disambiguate." Push all matching-rule prose into the script's `--help` and an inline comment. This eliminates the prose-vs-script drift surface that doomed `generate-index.sh`.

**Deferred:** will be resolved in Spec by asking the user — does the user want minimum-viable rewrite (single instruction + reference to script `--help`) or full preservation (current prose intact, with script as preferred path)? This affects perceived clarity of the skill itself.
