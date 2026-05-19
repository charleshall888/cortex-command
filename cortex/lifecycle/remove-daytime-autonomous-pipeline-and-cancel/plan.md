# Plan: remove-daytime-autonomous-pipeline-and-cancel

## Overview

Mechanical-but-bisect-safe removal sweep landing as a series of per-task commits — Phase 1's 3 pre-flight commits, Phase 2's atomic deletion commit, Phase 3's atomic dashboard commit, Phase 4's 6 independent code-hygiene commits, and Phase 5's 4 sequenced commits (~15 commits total). Phase 2 (atomic deletion) and Phase 3 (atomic dashboard refactor) are bundled into single tasks because pytest collection and template/poller coupling respectively forbid intermediate states. Phase 4's six code-hygiene tasks are genuinely independent (different files, no coupling) and ship as per-task commits. Phase 5's four tasks (TERMINAL_STATUSES extension, #228 cancellation, #230 annotation, CHANGELOG entry) are sequenced via `Depends on` and the `superseded`-cascade dependency is resolved by invoking the backlog updater via `python3 -m cortex_command.backlog.update_item` (which imports from the working-tree `common.py`, not from the installed wheel's site-packages copy).

## Outline

### Phase 1: Pre-flight verification + new tests (tasks: 1, 2, 3)
**Goal**: Land structural pins protecting against sibling-PR revert and providing forward-going regression coverage for the worktree-interactive dispatch surface.
**Checkpoint**: `pytest tests/test_lifecycle_implement_md_daytime_free.py tests/test_implement_worktree_interactive_contract.py` exits 0; `just test` exits 0; 3 Phase 1 commits on the working branch.

### Phase 2: Atomic deletion sweep (task: 4)
**Goal**: Delete daytime modules, tests, console-scripts, parity-exception rows, .gitignore patterns, audit allowlist entries, justfile recipe, and state.py daytime symbols in one bisect-safe commit.
**Checkpoint**: `find cortex_command/overnight -maxdepth 1 -name 'daytime_*.py' -o -name 'readiness.py' | wc -l` = 0; `just test` exits 0; 1 Phase 2 commit on the working branch.

### Phase 3: Atomic dashboard PR-url adaptation + daytime cleanup (task: 5)
**Goal**: In one atomic commit, add the worktree-interactive `pr.json` parser + `feature_pr` dataclass field, swap the template, remove daytime parsers / dataclass fields / call sites, and add the new dashboard PR-url test. Atomicity is load-bearing — between-task intermediate states would have template references with no poller population, or poller fields with no template consumers, breaking existing dashboard tests.
**Checkpoint**: `grep -rcn 'parse_daytime\|write_daytime_artifacts\|feature_daytime_\|daytime_state\|daytime_result' cortex_command/dashboard/` aggregates to 0; new test asserting feature_pr rendering passes; `just test` exits 0; 1 Phase 3 commit on the working branch.

### Phase 4: Code-hygiene + docs + registries (tasks: 6, 7, 8, 9, 10, 11)
**Goal**: Sweep `auth.py` / `cli_handler.py` / runner.py / interactive_lock.py / `_interactive_overnight_check.sh` / events-registry / observability catalog / docs / pipeline metrics docstring; retain `_DAYTIME_DISPATCH_FIELDS` as compat shim. Tasks are independent (different files, no coupling) and ship as 6 per-task commits.
**Checkpoint**: `grep -c daytime` against the swept paths returns expected zero counts (or expected ≥1 only for the retained `_DAYTIME_DISPATCH_FIELDS` filter and its test); `just test` exits 0; 6 Phase 4 commits on the working branch.

### Phase 5: TERMINAL_STATUSES + backlog cancellation + CHANGELOG (tasks: 12, 13, 14, 15)
**Goal**: Extend `TERMINAL_STATUSES` with `superseded`, cancel #228 via supersedence, annotate #230, and land the CHANGELOG `### Removed` entry. Tasks 12→13→14 are sequenced via `Depends on`. Task 13's invocation uses `python3 -m cortex_command.backlog.update_item` (not the wheel-installed `cortex-update-item` binstub) so the cascade at `update_item.py:409` reads the working-tree `TERMINAL_STATUSES` extended by Task 12. Task 15 (CHANGELOG) is independent.
**Checkpoint**: #228 frontmatter `status: superseded` with a `## Superseded by #246` body section AND #228's UUID absent from any extant `blocked_by` array (cascade-fired evidence); #230 retains `status: complete` with a body annotation; CHANGELOG contains the verbatim `uv tool uninstall cortex-command && uv tool install ...` migration note; `just test` exits 0; 4 Phase 5 commits on the working branch.

## Tasks

### Task 1: Verify `implement.md` is daytime-free at PR base
- **Files**: skills/lifecycle/references/implement.md (read-only — no modification)
- **What**: Pre-flight verification per R1. Confirm that the worktree-interactive replacement (siblings #238/#240) has already removed all daytime references from `implement.md` at the current PR base (whatever HEAD `main` is at the time this task runs) before this PR's pin test is added.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: Sibling work is expected to have already removed daytime tokens; this task does no edit, only confirms the precondition by running the grep at current HEAD. The matching pin test (Task 2) will lock the invariant in CI. Do not hardcode a specific commit SHA — anchor on the grep result.
- **Verification**: `grep -c 'Daytime Dispatch\|cortex-daytime' skills/lifecycle/references/implement.md` outputs `0` — pass if count = 0.
- **Status**: [x] complete (inline pre-flight: grep returned 0)

### Task 2: Add structural pin test for `implement.md` daytime-free invariant
- **Files**: tests/test_lifecycle_implement_md_daytime_free.py (new file)
- **What**: Per R2, create a structural pin test that fails if any future change re-introduces `"cortex-daytime"` or `"Daytime Dispatch"` tokens into `skills/lifecycle/references/implement.md`. Guards against sibling-PR revert per Adversarial F15.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Test asserts both `"cortex-daytime" not in open("skills/lifecycle/references/implement.md").read()` and `"Daytime Dispatch" not in open("skills/lifecycle/references/implement.md").read()`. Look at neighbor tests in `tests/` for the pytest layout idiom this repo uses (no fixtures needed — straight `open().read()` + `assert`). Single test function `test_implement_md_is_daytime_free()` is sufficient.
- **Verification**: `pytest tests/test_lifecycle_implement_md_daytime_free.py` exits 0 — pass if exit 0.
- **Status**: [x] complete (commit 2951acdd)

### Task 3: Add structural contract test for worktree-interactive dispatch surface
- **Files**: tests/test_implement_worktree_interactive_contract.py (new file)
- **What**: Per R3, create a structural contract test asserting that `skills/lifecycle/references/implement.md` (a) contains the menu label `"Implement on feature branch with worktree"` in §1; (b) invokes `cortex-interactive-lock acquire {slug}` at least once in the worktree-interactive dispatch block at §1a; (c) fires BOTH overnight-active rejection guards — pre-creation at §1 Step A AND post-creation at §1a.ii — via `_interactive_overnight_check.sh` (or the canonical guard sidecar from #241). Structural-only — no live SDK dispatch.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Pattern: read `skills/lifecycle/references/implement.md` once at test-module scope; assert each of the three substrings or `re.findall` patterns is present at minimum the required count. The guard test is "count of `_interactive_overnight_check.sh` references ≥ 2" — do not assert location precisely (line numbers drift), only that two distinct call sites exist. Scoped narrower than deleted `test_daytime_preflight.py` per the spec's R3 — not a verbatim coverage replacement. Test does NOT assert lock-release behavior (owned by lifecycle complete flow, not dispatch block).
- **Verification**: `pytest tests/test_implement_worktree_interactive_contract.py` exits 0 — pass if exit 0.
- **Status**: [x] complete (commit d74de579)

### Task 4: Phase 2 atomic deletion sweep — modules + tests + console-scripts + state.py + registries + justfile + .gitignore + audit allowlist
- **Files**:
  - DELETE: cortex_command/overnight/daytime_pipeline.py
  - DELETE: cortex_command/overnight/daytime_dispatch_writer.py
  - DELETE: cortex_command/overnight/daytime_result_reader.py
  - DELETE: cortex_command/overnight/readiness.py
  - DELETE: cortex_command/overnight/tests/test_daytime_pipeline.py
  - DELETE: cortex_command/overnight/tests/test_daytime_auth.py
  - DELETE: cortex_command/overnight/tests/test_daytime_result_reader.py
  - DELETE: cortex_command/overnight/tests/test_dispatch_readiness.py
  - DELETE: tests/test_daytime_preflight.py
  - DELETE: tests/test_daytime_dispatch_writer.py
  - DELETE: tests/test_dispatch_parity.py
  - MODIFY: pyproject.toml (lines 32-34 — remove three `cortex-daytime-*` console-scripts)
  - MODIFY: cortex_command/overnight/state.py (drop `DaytimeResult` line 67 + `save_daytime_result` lines 517-535)
  - MODIFY: bin/.parity-exceptions.md (lines 22-24 — remove three daytime console-script rows)
  - MODIFY: .gitignore (lines 32-34 — remove daytime tempfile patterns)
  - MODIFY: bin/.audit-bare-python-m-allowlist.md (remove 3 entries: launchd recipe at lines 22-32 + 2 `test_daytime_preflight.py` entries at lines 36-46 and 50-60)
  - MODIFY: justfile (lines 447-559 — remove `test-dispatch-parity-launchd-real` recipe)
- **What**: One atomic commit (R4 + R5 + R6 + R7 + R8 + R9 + R10 + R11) deleting all coupled daytime artifacts. The atomicity is load-bearing — pytest crashes at collection if module-import-level references in test files survive across commits where modules are deleted (Adversarial F12), `[project.scripts]` entries pointing at deleted modules would fail `uv tool install --reinstall` between commits, and `bin/.parity-exceptions.md` rows survive past script removal would trip the parity linter.
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**: `readiness.py` is a true leaf — only `daytime_pipeline.py:42`, `test_dispatch_readiness.py:30`, `test_daytime_pipeline.py:30`, and `test_dispatch_parity.py:49` import it, and all four are being deleted. `DaytimeResult` and `save_daytime_result` are consumed only by `daytime_pipeline.py` and `test_daytime_pipeline.py`. Confirm caller enumeration with `grep -rn "DaytimeResult\|save_daytime_result" cortex_command/ tests/` before deleting state.py symbols — expect to find only the modules being deleted in the same commit. `test_dispatch_readiness.py` must be deleted in full (312 lines), not partially per the original ticket text — its lines 1-206 import from `cortex_command.overnight.readiness`, which will not exist. The `pyproject.toml` change is the three lines 32-34: `cortex-daytime-dispatch-writer`, `cortex-daytime-pipeline`, `cortex-daytime-result-reader`. After all file ops, run `just test` to confirm no surviving import references (must pass before commit).
- **Verification**: All of the following must pass at commit time:
  - `find cortex_command/overnight -maxdepth 1 -name 'daytime_*.py' -o -name 'readiness.py' | wc -l` = 0
  - `find . -name 'test_daytime_*.py' -not -path '*/worktrees/*'` outputs nothing
  - `ls tests/test_dispatch_parity.py cortex_command/overnight/tests/test_dispatch_readiness.py 2>&1 | grep -c 'No such'` = 2
  - `grep -c 'cortex-daytime' pyproject.toml` = 0
  - `grep -c 'cortex-daytime-' bin/.parity-exceptions.md` = 0
  - `grep -c 'DaytimeResult\|save_daytime_result' cortex_command/overnight/state.py` = 0
  - `grep -c 'test-dispatch-parity-launchd-real' justfile` = 0
  - `grep -c 'daytime' .gitignore` = 0
  - `grep -c 'daytime' bin/.audit-bare-python-m-allowlist.md` = 0
  - `just test` exits 0
- **Status**: [x] complete (commit cc76eb1f)

### Task 5: Phase 3 atomic dashboard refactor — add `feature_pr` reader, swap template, remove daytime parsers + fields + call sites, add PR-url test
- **Files**:
  - MODIFY: cortex_command/dashboard/data.py (add `parse_feature_pr_artifact`; remove `parse_daytime_state` lines 1365-1373 and `parse_daytime_result` lines 1374-1380)
  - MODIFY: cortex_command/dashboard/poller.py (add `feature_pr` dataclass field + populator; remove daytime imports lines 33-34, remove `feature_daytime_state` and `feature_daytime_result` dataclass fields lines 106-107, remove the daytime comment at line 269 AND the call sites at lines 278-283 — the prose lists the comment and call sites separately so both get removed)
  - MODIFY: cortex_command/dashboard/seed.py (remove `write_daytime_artifacts` lines 827-887, caller at line 1185, comment line 592)
  - MODIFY: cortex_command/dashboard/templates/feature_cards.html (remove daytime template block at lines 39-40 and 127-141; remove second `pr_url` site at line 245; add `{% if feature_pr.get(slug) %}<a href="{{ feature_pr[slug].url }}">PR #{{ feature_pr[slug].number }}</a>{% endif %}` at the canonical PR-url render location)
  - NEW: cortex_command/dashboard/tests/test_feature_cards_pr_url.py (seeds a fixture lifecycle dir with populated `pr.json`, asserts non-empty `<a href="https://github.com/...">PR #N</a>` anchor; seeds a second fixture WITHOUT `pr.json`, asserts no PR anchor)
- **What**: One atomic commit covering R12 + R13. Atomicity is load-bearing — between-task intermediate states (e.g., template referencing `feature_pr` before poller populates it; daytime helpers removed before template is swapped) would break existing dashboard tests that assert daytime rendering. By doing all of it in one commit, the diff transitions from coherent-daytime-state to coherent-feature_pr-state without an inconsistent intermediate.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: `parse_feature_pr_artifact(lifecycle_dir: Path) -> dict | None` reads `cortex/lifecycle/{slug}/pr.json`. The canonical schema is defined in `skills/lifecycle/references/complete.md` lines 56-62 (5 fields: `number`, `url`, `head_branch`, `opened_at`, `repo`); the parser only needs to surface `url` and `number` for the template render, but should tolerate `opened_at` and other fields without raising. Parser handles `FileNotFoundError`, `json.JSONDecodeError`, and missing required keys by returning `None` — caller treats `None` as "no PR yet". Pattern reference for return-type convention: existing per-feature artifact readers like `parse_feature_events` and `parse_feature_timestamps` in `data.py`. The new `feature_pr: dict[str, dict] = field(default_factory=dict)` field on `DashboardState` replaces both `feature_daytime_state` and `feature_daytime_result` for PR-url purposes. Caller enumeration for the removed helpers: `parse_daytime_state` / `parse_daytime_result` are consumed only by `poller.py`; `write_daytime_artifacts` is consumed only by `seed.py:1185` (internal) — confirm via `grep -rn` before deletion. Template line numbers drift as daytime blocks are removed — locate the blocks by content, not absolute line numbers.
- **Verification**: All of the following must pass at commit time:
  - `grep -rcn 'parse_daytime_state\|parse_daytime_result\|write_daytime_artifacts\|feature_daytime_state\|feature_daytime_result\|daytime_state\|daytime_result' cortex_command/dashboard/ | awk -F: '{s+=$NF} END {print s}'` = 0
  - `grep -c 'daytime_result\|daytime_state' cortex_command/dashboard/templates/feature_cards.html` = 0
  - `grep -c 'feature_pr\[\|feature_pr\.get' cortex_command/dashboard/templates/feature_cards.html` ≥ 1
  - `pytest cortex_command/dashboard/tests/test_feature_cards_pr_url.py` exits 0
  - `just test` exits 0
- **Status**: [x] complete (commit 8a68d4bd)

### Task 6: Retitle `_DAYTIME_DISPATCH_FIELDS` docstring to compat-shim
- **Files**: cortex_command/pipeline/metrics.py
- **What**: Per R14, retitle the `_DAYTIME_DISPATCH_FIELDS` docstring at lines 360-362 to: `"Historical compatibility — skip pre-#246 daytime-schema rows in archived event logs."` Filter code at line 335 and consumer at line 422 are RETAINED — they prevent contamination of historical metric aggregation from archived `pipeline-events.log` rows on operator machines (Adversarial F6). Test at `cortex_command/pipeline/tests/test_metrics.py` `test_daytime_schema_skipped` (lines 216-246) is RETAINED.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Single-file docstring rewrite. Filter implementation and test untouched.
- **Verification**:
  - `grep -c '_DAYTIME_DISPATCH_FIELDS' cortex_command/pipeline/metrics.py` ≥ 1
  - `grep -c 'Historical compatibility' cortex_command/pipeline/metrics.py` ≥ 1
  - `pytest cortex_command/pipeline/tests/test_metrics.py -k test_daytime_schema_skipped` exits 0
- **Status**: [x] complete (commit 5c94c579)

### Task 7: Clean up `auth.py` — module/function docstrings + argparse description
- **Files**: cortex_command/overnight/auth.py
- **What**: Per R15, rewrite module docstring (line 1), function docstrings at lines 5, 301, 312, and the argparse `description=` string at line 553 to drop all daytime mentions. New argparse description: `"Resolve the SDK auth vector for the overnight runner."`
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Single-file prose edit. Adversarial F2 flagged that argparse `description=` text is vulture-blind — must hand-edit. After edit, `--help` output must not surface daytime tokens.
- **Verification**:
  - `grep -c 'daytime' cortex_command/overnight/auth.py` = 0
  - `python3 -m cortex_command.overnight.auth --help 2>&1 | grep -c daytime` = 0
- **Status**: [x] complete (commit ebf8a680)

### Task 8: Drop Sphinx xref + update events-registry `auth_probe` row
- **Files**: cortex_command/overnight/cli_handler.py, bin/.events-registry.md
- **What**: Per R16, remove or rewrite the `:func:` Sphinx xref to `daytime_pipeline._read_test_command` at `cli_handler.py:61`. Per R17, update `bin/.events-registry.md:119` `auth_probe` row's consumer column (drop `daytime_pipeline.py (verify_dispatch_readiness)` reference) and notes column (drop daytime-pipeline-specific behavior wording per Adversarial F14).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: For `cli_handler.py:61`, rewriting to reference the canonical surviving auth helper (e.g. `cortex_command.overnight.auth.ensure_sdk_auth`) preserves the xref's value; alternatively, delete the line entirely if it was only referenced for daytime-specific context. For `events-registry.md`, examine surrounding rows to confirm the column format before editing — the registry uses pipe-delimited columns with specific consumer-list formatting.
- **Verification**:
  - `grep -c 'daytime_pipeline' cortex_command/overnight/cli_handler.py` = 0
  - `grep -c 'daytime_pipeline' bin/.events-registry.md` = 0
- **Status**: [x] complete (commit 2d1dc644)

### Task 9: Rewrite orphan comments in runner.py, interactive_lock.py, _interactive_overnight_check.sh
- **Files**: cortex_command/overnight/runner.py, cortex_command/interactive_lock.py, skills/lifecycle/references/_interactive_overnight_check.sh
- **What**: Per R18, rewrite three orphan comments left behind after daytime removal:
  - `runner.py:2048` → rewrite to policy-invariant: `"Auth path uses ensure_sdk_auth + probe_keychain_presence (single policy)"` (Adversarial F11).
  - `interactive_lock.py:169` → rewrite to drop "no equivalent of daytime's stale-recovery helper" reference; keep the surrounding comment's substance but reword without the daytime reference.
  - `_interactive_overnight_check.sh:3` → rewrite to drop the "daytime mirror (implement.md §1a.iii, R8)" reference (Adversarial F4).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Pure comment edits; no logic change. The implement.md §1a.iii reference is itself dangling because §1a is now the worktree-interactive alternate path, not a daytime mirror. Note that `skills/lifecycle/references/_interactive_overnight_check.sh` is canonical and gets mirrored to `plugins/cortex-core/skills/lifecycle/references/_interactive_overnight_check.sh` via the dual-source pre-commit hook — edit only the canonical file.
- **Verification**: `grep -c 'daytime' cortex_command/overnight/runner.py cortex_command/interactive_lock.py skills/lifecycle/references/_interactive_overnight_check.sh` = 0.
- **Status**: [x] complete (commit af47e086)

### Task 10: Update observability catalog
- **Files**: cortex/requirements/observability.md
- **What**: Per R19, remove the two daytime module references (`daytime_pipeline`, `daytime_result_reader`) from the "Non-install-mutation (no guard call needed)" catalog at `cortex/requirements/observability.md:144`. Mechanical catalog cleanup.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Single-file edit. The catalog is a list of modules — drop the two daytime rows; do not restructure neighbors.
- **Verification**: `grep -c 'daytime' cortex/requirements/observability.md` = 0.
- **Status**: [x] complete (commit 1b6ae623)

### Task 11: Update docs (setup.md, overnight-operations.md, internals/sdk.md, release-process.md, index.html orphan CSS)
- **Files**: docs/setup.md, docs/overnight-operations.md, docs/internals/sdk.md, docs/release-process.md, docs/index.html
- **What**: Per R20, remove daytime references from:
  - `docs/setup.md` lines 121 and 214 (second reference was missed by ticket text, found in research)
  - `docs/overnight-operations.md` lines 227, 686, 697, 707-714 — including the entire "Daytime entry point: deferred-event-emit pattern" subsection at 707-714
  - `docs/internals/sdk.md` lines 7 and 17
  - `docs/release-process.md:124` — replace the #230 citation with a generic release-gate example description (per Adversarial F7: do not preserve the dangling reference)
  - `docs/index.html` — remove orphan `.daytime` CSS rules at lines 205, 919, 929, 931, 939, 949 and comments at 918, 2075. No HTML element uses `class="daytime"` (verified by grep), so the CSS is dead. Out of original R20 scope; surfaced by critical review. Keeping the orphan CSS would leave `docs/` with 8 surviving "daytime" tokens that the Acceptance grep would count.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Pure prose / CSS edits. The 707-714 subsection in `overnight-operations.md` is a whole-subsection delete (not a line-by-line trim). Per CLAUDE.md, the overnight docs source-of-truth split is: `docs/overnight-operations.md` owns the round loop and orchestrator behavior; `docs/internals/sdk.md` owns SDK model-selection mechanics — edits should preserve that separation. The release-process.md:124 replacement should be a generic phrase (e.g. "a representative release-gate ticket") rather than naming a specific backlog item. For `docs/index.html`, removing the `.daytime` CSS may leave the adjacent `.runner` / sibling-class rules visually unaffected — verify by loading the page locally after edit if convenient, but no functional regression expected since no element uses the class.
- **Verification**: `grep -c daytime docs/setup.md docs/overnight-operations.md docs/internals/sdk.md docs/release-process.md docs/index.html | awk -F: '{s+=$NF} END {print s}'` = 0.
- **Status**: [x] complete (commit 9eb82b99)

### Task 12: Add `superseded` to TERMINAL_STATUSES + `normalize_status` map + module-local `_TERMINAL`
- **Files**: cortex_command/common.py, cortex_command/overnight/plan.py, cortex_command/tests/test_terminal_statuses.py (new)
- **What**: Per R21, add `"superseded"` to: (a) `TERMINAL_STATUSES` frozenset at `cortex_command/common.py:162-170` (insert as new member of the frozenset literal); (b) `normalize_status` map at `cortex_command/common.py:769-778` (map `"superseded"` → `"superseded"` — self-map); (c) module-local `_TERMINAL` frozenset at `cortex_command/overnight/plan.py:213` (NOT imported from common.py — independent module-local set that filters the overnight session-plan "Not Ready" section at line 216). Add new test at `cortex_command/tests/test_terminal_statuses.py` asserting both `"superseded" in TERMINAL_STATUSES` and `"superseded" in cortex_command.overnight.plan._TERMINAL`.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: This task extends the cancellation-vocabulary frozenset (LOAD-BEARING for Adversarial F1 → Tradeoffs C1). It must land in the working tree before Task 13 — but the gate is NOT "working tree state in the editor" — it is "the `cortex_command.common` module that the invocation in Task 13 imports". Task 13 resolves this by invoking `python3 -m cortex_command.backlog.update_item` from the repo root (which inserts cwd as `sys.path[0]` and imports `cortex_command.common` from the working tree), not the wheel-installed `cortex-update-item` binstub (whose shebang pins the uv tool venv interpreter that imports from `~/.local/share/uv/tools/cortex-command/.../site-packages/cortex_command/common.py`). Note that the existing NOTE at `cortex_command/common.py:159` flags a second tuple at `overnight/backlog.py:40`, but inspection shows that line is the broader `STATUSES` validation enum (not a terminal-statuses tuple); `overnight/backlog.py` already imports `TERMINAL_STATUSES` from `common.py:28`, so this PR's extension propagates there automatically. The `common.py:159` NOTE itself is left unedited (its correction is a separate follow-up). The new test should import both names and assert membership — minimal, targeted test.
- **Verification**:
  - `grep -c '"superseded"' cortex_command/common.py` ≥ 2
  - `grep -c '"superseded"' cortex_command/overnight/plan.py` ≥ 1
  - `pytest cortex_command/tests/test_terminal_statuses.py` exits 0
- **Status**: [x] complete (commit 5fa76c54)

### Task 13: Cancel #228 — set `status: superseded` via working-tree-aware invocation + append `## Superseded by #246` body section
- **Files**: cortex/backlog/228-wire-daytime-dispatch-through-cli-and-mcp-with-launchd-detachment.md
- **What**: Per R22, run from the repo root: `python3 -m cortex_command.backlog.update_item 228-wire-daytime-dispatch-through-cli-and-mcp-with-launchd-detachment status=superseded`. This invocation (NOT the wheel-installed `cortex-update-item` binstub) imports `cortex_command.common` from the working tree, so the `superseded` member added by Task 12 is in the active `TERMINAL_STATUSES` set at `update_item.py:409`'s cascade gate. The cascade (`_remove_uuid_from_blocked_by`, `_check_and_close_parent`) fires correctly. Then append a `## Superseded by #246` body section pointing at this discovery (`cortex/research/swap-daytime-autonomous-for-worktree-interactive/research.md`) and parent epic #237.
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: Invocation form is load-bearing — see Risks for the wheel-vs-source resolution. The binstub at `~/.local/bin/cortex-update-item` is a symlink to the uv tool venv's binstub, whose shebang pins the venv interpreter that imports `cortex_command.common` from `~/.local/share/uv/tools/cortex-command/.../site-packages/`. That site-packages copy does NOT have `superseded` in `TERMINAL_STATUSES` until the wheel is reinstalled. By contrast, `python3 -m cortex_command.backlog.update_item` from the repo root inserts cwd into `sys.path[0]`, so `cortex_command.common` resolves to the working-tree copy with Task 12's extension applied — the cascade gate sees `superseded` as terminal and fires correctly. The body section should reference the cortex research path so future readers reach the rationale. Pattern reference: `cortex/backlog/211-*.md` and `cortex/backlog/212-*.md` both have `## Superseded by #213` body sections — match that shape.
- **Verification**: All of the following must pass:
  - `grep -c '^status: superseded' cortex/backlog/228-wire-daytime-dispatch-through-cli-and-mcp-with-launchd-detachment.md` = 1
  - `grep -c '## Superseded by' cortex/backlog/228-wire-daytime-dispatch-through-cli-and-mcp-with-launchd-detachment.md` = 1
  - Cascade-fired evidence: extract #228's `uuid:` from frontmatter, then `grep -rn "<uuid>" cortex/backlog/ | grep -i 'blocked_by'` returns nothing (the cascade removes #228's UUID from any `blocked_by` array). If no extant `blocked_by:` chain references #228 today, the grep returns nothing regardless and the cascade-fired evidence is vacuously satisfied — confirm this baseline with `grep -rn "228-wire-daytime-dispatch" cortex/backlog/*.md` (excluding #228 itself) before running Task 13 so the verification is meaningful.
- **Status**: [x] complete (commit 4814cc3a; baseline confirmed no extant blocked_by chains, cascade vacuously satisfied)

### Task 14: Annotate #230 body — do NOT change frontmatter
- **Files**: cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md
- **What**: Per R23, append a body section to #230 noting "Parent #228 cancelled via #246; release-gate procedure no longer applies." Frontmatter `status: complete` is RETAINED — the release-gate completion is real history and is not retroactively rewritten (Tradeoffs C resolution).
- **Depends on**: [13]
- **Complexity**: simple
- **Context**: Direct markdown body edit; do not invoke any backlog-updater for this one (no status change). The section heading should clearly distinguish "completed work history" from "current applicability" so future readers don't mistake the annotation for a status downgrade. Suggested section: `## Update — Parent #228 cancelled via #246`.
- **Verification**:
  - `grep -c '^status: complete' cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` = 1
  - `grep -c 'release-gate procedure no longer applies' cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` = 1
- **Status**: [x] complete (commit 0a79e94c)

### Task 15: Add CHANGELOG `### Removed` entry with operator-action migration note
- **Files**: CHANGELOG.md
- **What**: Per R24, add a `### Removed` block under `[Unreleased]` documenting: (a) what was removed — three daytime modules + `readiness.py`, three console-scripts, seven test files, dashboard daytime surfaces, justfile dispatch-parity recipe, `.gitignore` patterns; (b) what replaces it — "worktree-interactive implement-phase option, delivered by #238 + #240 under epic #237"; (c) the verbatim operator-action note: `"Run \`uv tool uninstall cortex-command && uv tool install git+<url>@<latest-tag>\` to remove orphan \`cortex-daytime-*\` binstubs from \`~/.local/bin/\`. \`uv tool install --reinstall\` is not sufficient — it does not remove binstubs whose entry-points are no longer in \`[project.scripts]\`."`
- **Depends on**: [14]
- **Complexity**: simple
- **Context**: CHANGELOG precedent at lines 71-82 and line 75 (`/fresh,/evolve,/retro` retirement) is the closest pattern — multi-paragraph inline `### Removed` entry under `[Unreleased]`. The verbatim migration text is REQUIRED per spec Technical Constraints — `uv tool install --reinstall` does not remove orphan binstubs (Adversarial F9/S1), only `uv tool uninstall && uv tool install` does. Push to main with this commit (`pyproject.toml` + `CHANGELOG.md` changes) will trigger `.github/workflows/auto-release.yml`; operator coordinates merge window externally per Technical Constraints.
- **Verification**:
  - `grep -c '### Removed' CHANGELOG.md` ≥ 1
  - `grep -c 'uv tool uninstall cortex-command' CHANGELOG.md` ≥ 1
  - `just test` exits 0 (final whole-feature check per R25)
- **Status**: [x] complete (commit 1fbec14d)

## Risks

- **TERMINAL_STATUSES install-layer dependency (Tasks 12-13)**: The cascade gate at `update_item.py:409` reads `TERMINAL_STATUSES` at invocation time. The wheel-installed `cortex-update-item` binstub imports `cortex_command.common` from the uv tool venv's site-packages — NOT from the working tree — so Task 12's working-tree edit would not affect a binstub invocation in Task 13. Task 13's plan resolves this by invoking `python3 -m cortex_command.backlog.update_item` from the repo root, which inserts cwd into `sys.path[0]` and imports `cortex_command.common` from the working tree. Reviewer should confirm this invocation form is acceptable (versus an alternative resolution like adding an explicit `uv tool install --reinstall` step before Task 13, which would be heavier and slower). The cascade-fired evidence in Task 13's Verification is forward-looking — there are no extant `blocked_by: [228]` chains today (#230 uses snake_case `blocked_by` but the cascade regex matches kebab-case, so it doesn't match), but the load-bearing benefit is for any future `blocked_by: [228]` chain.
- **TERMINAL_STATUSES extension scope (Task 12)**: Adding `superseded` to the frozenset is a deliberate co-edit for the cancellation vocabulary, per Tradeoffs § C1 / Adversarial F1. The alternative (defer to follow-up + use `wontfix` instead) loses the semantically correct vocabulary and creates a worst-of-both-worlds state where `superseded` is neither eligible nor terminal. Reviewer should confirm this scope expansion is acceptable rather than the deferred alternative.
- **`_DAYTIME_DISPATCH_FIELDS` filter retention (Task 6)**: The original ticket text said to delete this filter, but research reclassified it as a read-side compat shim for archived `pipeline-events.log` rows on operator machines (Adversarial F6 → Tradeoffs § H1). Reviewer should confirm "keep + retitle docstring" is the right call vs full deletion. Deletion would contaminate historical metric aggregation on every operator machine with archived daytime events.
- **Phase 2 single-commit atomicity (Task 4)**: The atomic-commit constraint forces a `complex` task touching 11+ files. The alternative (split across multiple commits) is broken — pytest collection crashes on `from cortex_command.overnight.readiness import ...` after `readiness.py` is deleted. Reviewer should confirm the atomicity is unavoidable.
- **Phase 3 atomic dashboard bundling (Task 5)**: The dashboard refactor is bundled into one atomic commit (not split into reader/template/cleanup tasks) because between-task intermediate states would break existing dashboard tests — e.g., after a hypothetical template-swap-only commit, daytime tests asserting daytime rendering would fail. Reviewer should confirm the bundling shape is acceptable versus per-task ordering (which would require reordering daytime-test-deletion before template-change).
- **Worktree-interactive contract test scope (Task 3)**: R3's test is structural-only (asserts text patterns in `implement.md`) and is narrower than the deleted `test_daytime_preflight.py` (which covered PID-liveness, polling-fallback, outcome detection on a live SDK surface). Not a verbatim coverage replacement — Spec's "Changes to Existing Behavior" explicitly accepts this delta. Reviewer should confirm this is the right scope vs adding a live-SDK contract test.
- **PR-url rendering is fresh, not continuity (Tasks 5)**: The plan frames the dashboard refactor as adapting an existing PR-url render to a new schema, but in fact no extant lifecycle has ever populated the prior daytime `pr_url` field (all three live `daytime-result.json` artifacts in `cortex/lifecycle/` carry `pr_url: null`; no `pr.json` exists anywhere in the repo today). The dashboard render added in Task 5 will be fixture-only until a future post-#240 lifecycle naturally writes `pr.json` from the complete-phase Step 4 prose protocol in `skills/lifecycle/references/complete.md`. The reader/writer contract is enforced by prose adherence (no in-repo code under `cortex_command/`, `bin/`, `hooks/`, or `plugins/` writes `pr.json`); if a future model deviates from Step 4's snippet, every downstream lifecycle silently produces no anchor with no test-suite signal. Out of scope for this plan to fix the writer side; flag as a follow-up if architectural enforcement is desired.
- **Auto-release coordination (Task 15)**: Pushing the Phase 5 commit to main with `pyproject.toml` + `CHANGELOG.md` changes will trigger `auto-release.yml`. Operator coordinates the merge window externally — not enforced by this plan. Reviewer should be aware so the merge happens at a coordinated time.

## Acceptance

The complete feature succeeds when, on a checkout of the merged PR: (a) `just test` exits 0 with no daytime-related test files remaining (R25); (b) `find cortex_command/overnight -maxdepth 1 -name 'daytime_*.py' -o -name 'readiness.py' | wc -l` outputs 0; (c) `grep -rc daytime CHANGELOG.md cortex_command/ cortex/requirements/ docs/ bin/ skills/ tests/` produces a total count that matches ONLY the expected surviving references: the `_DAYTIME_DISPATCH_FIELDS` compat-shim in `cortex_command/pipeline/metrics.py` (and its test), the CHANGELOG `### Removed` entry's `cortex-daytime-*` migration text, and the #228/#230 backlog body annotations (#228 lives under `cortex/backlog/`, not the swept dirs, but the supersedence record may include the literal token); and (d) `cortex/backlog/228-*.md` has `status: superseded` while `cortex/backlog/230-*.md` retains `status: complete` with its body annotation, both verifying that the cancellation vocabulary lands without retroactive history rewrite.
