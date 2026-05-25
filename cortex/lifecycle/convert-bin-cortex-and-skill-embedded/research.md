# Research: Eliminate install-topology bug at four python3 -c callsites

Clarified intent: replace the bare `python3 -c "import cortex_command..."` pattern at four named callsites with a mechanism that survives `uv tool install` distribution. All four sites must end up with a graceful failure mode (no raw `ModuleNotFoundError`; no misdirecting "CLI not found" message when the CLI is in fact installed). Three mechanisms proposed: (a) shebang-resolve, (b) `cortex <subcommand>` namespace, (c) `[project.scripts]` console-script entries with bash-wrapper retirement.

## Codebase Analysis

### The four callsites in detail

**bin/cortex-backlog-ready** (21 lines) and **bin/cortex-morning-review-complete-session** (21 lines) share the identical three-branch wrapper pattern:

```bash
# Branch (a): packaged form — cortex_command.backlog.ready
if python3 -c "import cortex_command.backlog.ready" 2>/dev/null; then
    exec python3 -m cortex_command.backlog.ready "$@"
fi
# Branch (b): CORTEX_COMMAND_ROOT points at a cortex-command checkout ...
# Branch (c): not found
echo "cortex-backlog-ready: cortex-command CLI not found ..." >&2
```

Both bin wrappers also invoke `cortex-log-invocation` as a preamble (lines 2–4). Branch (a)'s probe is dead under `uv tool install` because the system `python3` does not have the per-tool venv on its sys.path; the wrapper falls through to branch (c)'s misdirecting error even when the CLI is correctly installed and on PATH.

**skills/critical-review/references/residue-write.md** — two inline `python3 -c` snippets:
- Lines 13–16: glob `cortex/lifecycle/*/.session` files to resolve the active feature slug from `$LIFECYCLE_SESSION_ID`.
- Lines 28–38: atomic JSON write of `critical-review-residue.json` via `tempfile.NamedTemporaryFile` + `os.replace`.

**skills/lifecycle/references/implement.md** — two inline `python3 -c` snippets that import library functions:
- Lines 28–29: `from cortex_command.lifecycle_config import read_branch_mode; print(read_branch_mode(...) or '')`
- Lines 37–38: `from cortex_command.lifecycle_implement import should_fire_picker; fire, reason = should_fire_picker(...); print(f'{fire}\t{reason}')`

### Prior art (option-b predecessor)

The predecessor lifecycle `resolve-cortex-interpreter-via-cli` shipped `cortex hooks scan-lifecycle` via lazy-dispatch in `cortex_command/cli.py` (dispatcher at lines 110–113, subparser at lines 717–740). The hook namespace is already wired and extensible. Extending to `cortex backlog ready`, `cortex morning-review complete-session`, etc. costs ~100 LOC of cli.py boilerplate per the codebase agent's count.

### Prior art (option-c — already partial)

`pyproject.toml` lines 21–57 already register **two of the four callsites** as `[project.scripts]` console-scripts:

```toml
cortex-backlog-ready = "cortex_command.backlog.ready:main"
cortex-morning-review-complete-session = "cortex_command.overnight.complete_morning_review_session:main"
```

A comment at line 28 (`# Phase 3 console-script sweep (R13): promoted from python3 -m callsites`) indicates an active migration cohort. The bash wrappers exist only as fallback. For these two callsites, option (c) reduces to "delete the wrapper + mirror" — the console-script is already there.

The two skill-embedded callsites in `implement.md` reference **library functions** (`read_branch_mode`, `should_fire_picker`) that do not have `main()` entry points. The two snippets in `residue-write.md` are bash-embedded code without any Python module structure. Promoting either to `[project.scripts]` requires authoring a new `main()`.

### Telemetry preamble

`bin/cortex-log-invocation` runs as the preamble in every `bin/cortex-*` wrapper. Failures are tolerated (`|| echo ... >&2`). Verified by the codebase agent: neither `cortex_command/backlog/ready.py:main()` nor `cortex_command/overnight/complete_morning_review_session.py:main()` invokes `_telemetry.log_invocation` from inside Python — only `update_item.py` and `create_item.py` do. Today, when invoked via the wheel-installed console-script (skipping the bash wrapper), these two **already have a silent telemetry hole**; the bash wrapper does the logging in branch (a)'s preamble.

### Parity / mirror enforcement

- `.githooks/pre-commit` Phase 1.5 (parity) and Phase 1.6 (shim-presence via `bin/cortex-invocation-report --check-shims`) trigger on `bin/cortex-*` staged paths. Phase 2 auto-mirrors `bin/` → `plugins/cortex-core/bin/` via `just build-plugin`.
- `bin/.parity-exceptions.md` allowlist: precedent (line 21) for `cortex-pipeline-metrics` shows the established pattern when retiring a wrapper: keep the `[project.scripts]` entry, optionally add allowlist row if scan-glob no longer finds the script name in any wiring source. The two bin/* targets here ARE still referenced from skill prose (e.g., `skills/backlog/SKILL.md`), so no allowlist row is needed after wrapper deletion.
- `tests/test_dual_source_reference_parity.py` enforces byte-identity of canonical bin/* vs mirror. Test gates also include `tests/test_check_parity.py`, `tests/test_lifecycle_kept_pauses_parity.py`, `tests/test_install_guard_parity.py`, `tests/test_skill_size_budget.py`.

## Web Research

- **`uv tool install` topology** ([docs.astral.sh/uv concepts/tools](https://docs.astral.sh/uv/concepts/tools/)): each tool gets a per-tool venv; entry points are symlinked (Unix) into the executable directory and point at the venv's `bin/`. The console-script wrapper's shebang targets the venv's interpreter — which is precisely why `python3 -c "import cortex_command"` against the system `python3` fails.
- **PyPA convention** ([packaging.python.org entry-points spec](https://packaging.python.org/en/latest/specifications/entry-points/)): console-scripts via `[project.scripts]` is the standard mechanism. Mature CLIs (black, ruff, mypy, poetry, hatch, pytest) ship exclusively this way; bash wrappers are legacy. Quote: `the entry point "mycmd = mymod:main" would create a command "mycmd" launching a script like this: import sys; from mymod import main; sys.exit(main())`.
- **Shebang-resolve (option a) precedent**: none found in major OSS. Shebang parsing is fragile under packager rewrites (debian, conda, nix, dh-virtualenv) and the kernel `BINPRM_BUF_SIZE` limit (historically 127 bytes, raised to 256 in Linux 5.1). Real-world projects instead use `python -m pkg` or invoke the venv interpreter directly.
- **`python3 -c "import pkg"` as install-probe**: actively wrong under PEP 668 / pipx / `uv tool`. The robust probe is `command -v <cli-name>` — "does the command exist on PATH?" — not "can the system Python import it?"
- **Subcommand-namespace extension (option b)**: dominant idiom for extensible CLIs. Git, kubectl, gh, docker all use the `<tool> <group> <verb>` pattern. The `cortex <group> <subcommand>` form already used by `cortex hooks scan-lifecycle` is standard.
- **Console-script startup-latency**: dominated by the importing package's import graph, not the number of `[project.scripts]` entries. Options (b) and (c) are equivalent on cold start; lean setuptools wrappers (`import sys; from pkg.mod import main; sys.exit(main())`) have negligible per-entry overhead.

## Requirements & Constraints

**project.md "Skill-helper modules" constraint** (line 35) — explicitly prescribes `[project.scripts]` console-script entries as the recommended idiom, with `python3 -m cortex_command.<skill>` as the readable fallback. Quote: "Promoted modules expose a `[project.scripts]` console-script entry (e.g. `cortex-<skill>`) as the recommended invocation idiom".

**project.md "Wheel-binstub vs working-tree invocation" constraint** (line 38) — describes the wheel-vs-source dual-channel pattern. Discusses `CORTEX_COMMAND_FORCE_SOURCE=1` for working-tree invocation. Provides context but does not directly ground the bare-`python3 -c` failure mode.

**ADR-0002 (CLI wheel + plugin distribution)** — the governing distribution model. The "dead branch (a)" bug exists precisely because branch (a)'s probe was written before the two-channel split formalized.

**project.md "SKILL.md-to-bin parity enforcement"** (line 33) — bin/cortex-* scripts must wire through an in-scope reference; `bin/cortex-check-parity` blocks drift; exceptions at `bin/.parity-exceptions.md`. Retiring a wrapper that still has references in skill prose does NOT require an allowlist row.

**CLAUDE.md Solution Horizon** — "Before suggesting a fix, ask whether you already know it will need to be redoing — because the same patch would apply in multiple known places you can name." This work explicitly identifies four such places. The principle is two-edged: it supports both a one-shot architectural fix AND a small probe-level fix, depending on whether a future redo is named.

**CLAUDE.md "Prescribe What and Why, not How"** — applies to skill prose rewrites. The fix is not just to swap the snippet; it is to rewrite the surrounding prose to describe the intent and let the agent (skill consumer) determine method.

**Tags `[skills, hooks, bin, install-topology]`** — none match project.md's Conditional Loading section; no area docs apply. `project.md` + `glossary.md (skipped: file absent)` only.

**Test gates**:
- `tests/test_dual_source_reference_parity.py` — byte-identity, canonical bin/* vs mirror
- `tests/test_check_parity.py` — parity linter
- `tests/test_lifecycle_kept_pauses_parity.py` — kept-pauses inventory; **see Adversarial F1 for blocker detail**
- `tests/test_skill_size_budget.py` — SKILL.md size cap; relevant if skill files grow

## Tradeoffs & Alternatives

### Per-option summary

| Dimension | (a) shebang-resolve | (b) `cortex <sub>` | (c) `[project.scripts]` |
|---|---|---|---|
| Implementation complexity | Low for bin/*; **inapplicable to skill snippets** (no wrapper to shebang-resolve) | Moderate (~100 LOC cli.py + 4 new main()s + skill rewrites) | Lowest for bin/* (two console-scripts already exist; delete wrappers); moderate for snippets (new modules + entries) |
| Maintainability | Worst — perpetuates bash three-branch + adds shebang-parse step | Best long-term — one cli.py owns dispatch; uniform `cortex X Y` model | Good for bin/*; per-callsite cost scales linearly for snippets |
| Performance | Two cold starts per invocation | One cold start; dominated by import graph | Same as (b) |
| Alignment | None — no OSS precedent; fragile | Matches `cortex hooks scan-lifecycle` predecessor | Matches project.md line 35 explicit prescription + 30+ existing entries |

### Per-callsite cost

- **bin/cortex-backlog-ready** and **bin/cortex-morning-review-complete-session**: (c) is cheapest — delete the canonical wrapper + mirror; the `[project.scripts]` entry already exists; no Python changes.
- **residue-write.md (two snippets)**: (a) inapplicable. (b) adds `cortex lifecycle resolve-feature` and `cortex critical-review write-residue` subcommands. (c) requires new modules with `main()` + new entries.
- **implement.md (two snippets)**: (a) inapplicable. (b) adds `cortex lifecycle read-branch-mode` and `cortex lifecycle should-fire-picker`. (c) wraps library functions with CLI surfaces.

### Initial recommendation (subject to adversarial revision below)

**Mixed: option (c) for the two bin/* callsites, option (b) for the four skill snippets.** Rationale: minimum diff at bin/* (console-scripts already exist, just delete wrappers), discoverability of grouped subcommands for skill helpers, uniform fail-clean behavior across all four, alignment with both documented patterns. Option (a) rejected outright.

**This recommendation does not survive the Adversarial Review unrevised** — see Open Questions for the spec to resolve.

## Adversarial Review

Twelve findings; the material ones:

- **F1 — Kept-pauses parity test regex collision**: `tests/test_lifecycle_kept_pauses_parity.py:42` defines `_CONDITIONAL_PAUSE_MARKER = re.compile(r"\bread_branch_mode\b|\blifecycle_config\b")` and requires one of those literal tokens within ±LINE_TOLERANCE of an inventoried bullet. `skills/lifecycle/references/implement.md:22` self-documents this: "The `read_branch_mode` invocation here is the **structural marker** that the parity test ... anchors against — its presence in this section is load-bearing for the documentation-parity test". Rewriting the snippet to `cortex lifecycle read-branch-mode` removes both literal tokens (CLI hyphenated form does not match `\bread_branch_mode\b`) and **the parity test will fail**. The spec must either keep the literal token in surrounding prose or extend the marker regex in the same PR. CLAUDE.md's "user-facing affordance protection" rule cites this scenario as the canonical example of what not to silently demolish.

- **F5 — Overlooked 5th option (probe-level fix)**: a one-line probe substitution — replace `python3 -c "import cortex_command..."` with `command -v cortex >/dev/null` (or `command -v cortex-backlog-ready >/dev/null` for the wrapper-specific probe) — fixes all four callsites with a ~4-line patch surface. Branch (a)'s `exec` line is unchanged; the probe just stops falsely failing under `uv tool install`. The same probe works for the skill snippets (clean diagnostic if the CLI is absent, no `ModuleNotFoundError`). This preserves all existing architecture, doesn't widen the CLI attack surface, doesn't break the parity test, doesn't tax `cortex --help`, doesn't widen skill prose. The ticket's "Proposed approach" framed the choice as (a)/(b)/(c) without naming (d) probe-substitution; Solution Horizon defaults to the simpler fix unless a future redo is named.

- **F2 — Telemetry helper is under-scoped**: the proposed "shared `main()`-prelude helper, ~30 LOC, one place" is incomplete. Today's promoted `main()` functions for the two bin/* targets do NOT uniformly call `_telemetry.log_invocation` — the bash wrapper does. Retiring the wrappers either (i) accepts a silent telemetry hole for two of the four callsites (which already exists today when those console-scripts are invoked directly via wheel), (ii) adds explicit telemetry calls to those two `main()`s, or (iii) requires a structural test/gate covering 25+ promoted entry points. Pick one explicitly in spec.

- **F6 — Three invocation forms is more inconsistency, not less**: Agent 4's mixed recommendation produces three live invocation forms for the same backlog logic (the console-script `cortex-backlog-ready` + the new `cortex backlog ready` subcommand + the existing `python3 -m cortex_command.backlog.ready` fallback). This contradicts Done-when (2)'s "consistent design choice is documented." Pick one primary invocation form per module.

- **F7 — Library functions ≠ hook CLIs**: the `cortex hooks scan-lifecycle` precedent generalizes poorly to `read_branch_mode` (returns `str|None`) and `should_fire_picker` (returns `tuple[bool, str]`). The hook had an established input/output contract; library functions don't. Each promotion introduces argparse, exit codes, stdout serialization, schema versioning — work Agent 4 elided as "small helper functions."

- **F8 — Active sibling lifecycle on same epic**: `cortex/lifecycle/skill-prose-to-cli-argparse-contract/` is actively designing a parity lint that scans skill markdown for `cortex-*` invocations and validates against `[project.scripts]` argparse surfaces. Adding `cortex lifecycle should-fire-picker` etc. to skill prose AND to `[project.scripts]` simultaneously creates immediate cross-lifecycle dependency. The two lifecycles must coordinate; this ticket cannot land in isolation.

Other findings (F3, F4, F9–F12) cover: `should_fire_picker` tab-stream output fragility (F3), path-traversal risk on `cortex critical-review write-residue` if `--feature` accepts arbitrary slug input (F4), the shim-presence gate's behavior on deletions (F9), the `cortex-pipeline-metrics` allowlist precedent (F10), upgrade timing risk for users with stale venvs (F11), and discoverability of internal-plumbing subcommands at `cortex lifecycle --help` (F12). These inform spec detail but do not invalidate the approach by themselves.

## Open Questions

The Adversarial Review surfaced seven questions. Resolutions reached after symmetric-defense re-research (defense-of-pure-c, defense-of-disciplined-mixed, neutral-comparator on predecessor and sibling lifecycle):

1. **Mechanism choice: pure (c) console-script for all six entry points.** Resolved. Option (d) probe-substitution fixes the bin/* wrappers' probe but not the skill snippets — the snippet body still does `python3 -c "import cortex_command..."` which fails under `uv tool install` regardless of any probe. The minimum-viable (d) for skill snippets requires resurrecting the `--print-python` flag the predecessor lifecycle explicitly retired in favor of the subcommand refactor (per `cortex/lifecycle/resolve-cortex-interpreter-via-cli/research.md:71-79`). So (d) is off the table for snippets on prior-art grounds. Option (b) `cortex <group> <verb>` is viable but the four helpers are not a coherent noun-group like `git remote *` — they are sequenced inline-flow predicates tightly coupled to one preflight block per skill, with no expansion pathway. The disciplined-mixed argument from F4 of the disciplined-mixed defense ("inventing `cortex-lifecycle-should-fire-picker` as a top-level binary is a category error") is mitigated by consolidating into **two** console-scripts each holding internal subcommands: `cortex-lifecycle-config` (branch-mode + picker-decision verbs) and `cortex-critical-review-residue` (resolve-feature + write verbs). This matches project.md:35 verbatim ("`python3 -m cortex_command.<skill> <subcommand>` is retained as a readable fallback" — the `<subcommand>` token implies modules expose internal verbs).

2. **F1 parity-test marker collision: extend the regex in the same PR.** Resolved. Renaming `read_branch_mode` / `lifecycle_config` Python tokens to CLI form (`cortex-lifecycle-config branch-mode`) breaks `tests/test_lifecycle_kept_pauses_parity.py:42`'s regex. The spec MUST update the regex to match the new invocation literal AND must keep the original Python identifier referenced in a comment near the new CLI invocation in implement.md (defense-in-depth). The parity test edit is mechanical; the marker just moves to the new literal.

3. **F6 one-form-per-module: pure (c) gives one form per module automatically.** Resolved. The four skill-helper modules expose their single canonical form via the consolidated console-scripts. The two bin/* modules expose their single canonical form via their existing `[project.scripts]` entries (`cortex-backlog-ready`, `cortex-morning-review-complete-session`). The `python3 -m cortex_command.<module>` fallback per project.md:35 stays available for ad-hoc invocation but is not invoked from skill prose. No `cortex <group> <verb>` parallel routing is added — F6 drift risk eliminated structurally.

4. **F2 telemetry: add explicit `_telemetry.log_invocation()` calls to each promoted `main()` + a structural test.** Resolved. Today's silent telemetry hole on `cortex_command.backlog.ready:main` and `cortex_command.overnight.complete_morning_review_session:main` is pre-existing (it fires when the console-script is invoked directly, skipping the bash wrapper preamble); retiring the wrappers exposes the gap to all invocations rather than just direct console-script invocations. Spec MUST add log_invocation calls to all six promoted `main()`s (the four new helpers + the two bin/* targets that already have console-scripts) AND author a structural test in `tests/` asserting every promoted entry point calls log_invocation. This prevents future promotion drift.

5. **F8 cross-lifecycle coordination with skill-prose-to-cli-argparse-contract: ship after sibling lifecycle's lint v1 lands.** Resolved by sequencing. The sibling lint's v1 includes nested-subparser introspection per its spec.md:14 (`add_subparsers`, `subparser .add_parser`), so the consolidated two-console-script-with-internal-verbs shape is supported. This lifecycle should ship AFTER the sibling lint v1 so the new surfaces are validated on first emission. Spec should declare the dependency and check the sibling lifecycle's status before opening this lifecycle's PR.

6. **F3/F4/F12 CLI surface details: JSON output, slug validation, hidden-from-help.** Resolved as spec-authoring details:
   - F3: `cortex-lifecycle-config picker-decision` emits structured JSON `{"fire": bool, "reason": "<closed-set-token>"}` instead of tab-separated text. Authoring a frozen-contract test asserting the reasons set is closed and tab-free.
   - F4: `cortex-critical-review-residue write --feature <slug>` validates `--feature` against `^[a-z0-9][a-z0-9-]*$` regex; reject otherwise with exit 2. Document the regex inline.
   - F12: discoverability — keep the two consolidated console-scripts as top-level (`cortex-lifecycle-config`, `cortex-critical-review-residue`) so they appear in `cortex-<TAB>` for skill authors; internal verbs are discovered via `<binary> --help`. No argparse SUPPRESS needed because the consolidation already groups the verbs naturally.

7. **F11 CHANGELOG: include `uv tool install --reinstall` remediation note.** Resolved. Spec includes a CHANGELOG entry listing the two deleted bash wrappers and the recommended remediation command for users with stale venvs.

All open questions resolved. Ready to proceed to Spec.
