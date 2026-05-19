# Research: Remove daytime autonomous pipeline and cancel #228/#230

Final removal sweep under epic #237 after the worktree-interactive replacement (siblings #238, #240) lands. Deletes daytime modules, tests, console-scripts, dashboard surfaces, and code-hygiene references across pipeline, overnight runner, dashboard, skills, and docs. Cancels in-flight ticket #228 (status `refined`) and annotates already-complete ticket #230 with a supersedence note.

## Codebase Analysis

### Files to change — verified inventory

**DELETE — modules (confirmed exist):**
- `cortex_command/overnight/daytime_pipeline.py`
- `cortex_command/overnight/daytime_dispatch_writer.py`
- `cortex_command/overnight/daytime_result_reader.py`
- `cortex_command/overnight/readiness.py` — confirmed leaf post-deletion. Sole production consumer is `daytime_pipeline.py:42`; surviving overnight modules (`runner.py`, `orchestrator.py`, `feature_executor.py`, `outcome_router.py`, `report.py`) do not import `readiness`.

**DELETE — tests (6 daytime-related + dispatch-parity):**
- `cortex_command/overnight/tests/test_daytime_pipeline.py`
- `cortex_command/overnight/tests/test_daytime_auth.py`
- `cortex_command/overnight/tests/test_daytime_result_reader.py`
- `tests/test_daytime_preflight.py`
- `tests/test_daytime_dispatch_writer.py`
- `tests/test_dispatch_parity.py`
- **CORRECTION**: `cortex_command/overnight/tests/test_dispatch_readiness.py` must be **deleted in full (312 lines)**, not partially. Lines 1-206 are unit tests of `readiness.verify_dispatch_readiness` itself — they import `from cortex_command.overnight.readiness import ReadinessResult, verify_dispatch_readiness` at line 30. With `readiness.py` deleted, those imports crash at collection. The ticket's "delete lines 207-301" instruction is structurally incompatible with deleting `readiness.py`. File extends to 312 lines, not 301.

**MODIFY — code with verified line ranges (drift corrections in bold):**
- `cortex_command/overnight/state.py` — drop `DaytimeResult` (line 67), `save_daytime_result` (line 517-535); verify no surviving callers via `grep -rn "DaytimeResult\|save_daytime_result"`.
- `cortex_command/overnight/auth.py` lines 1, 5, 301, 312, **553** — module/function docstrings + argparse `description=` string at line 553 (Adversarial F2: vulture-blind argparse text).
- `cortex_command/overnight/cli_handler.py:61` — Sphinx `:func:` xref to `daytime_pipeline._read_test_command`. Verified exists.
- `cortex_command/pipeline/metrics.py` — `_DAYTIME_DISPATCH_FIELDS` at **line 335 (not 324)**, consumer at **line 422 (not 414)**, docstring at lines 360-362. **Adversarial F6 reframe**: this filter is a **read-side compatibility shim**, not dead code. Historical `pipeline-events.log` archives on user machines still contain daytime-schema rows; removing the filter contaminates historical metric aggregation. See **Tradeoffs § H** below — recommend **keep the filter**, retitle docstring to "Historical compatibility — skip pre-#246 daytime-schema rows in archived event logs" rather than deleting.
- `cortex_command/pipeline/tests/test_metrics.py:212-248` — `test_daytime_schema_skipped` method. **Keep** if F6 mitigation is adopted; **delete** if filter is removed.
- `cortex_command/dashboard/data.py` — `parse_daytime_state` and `parse_daytime_result` at lines 1365-1380.
- `cortex_command/dashboard/poller.py` — imports lines 33-34; state fields 106-107; logic at 269, 278-283.
- `cortex_command/dashboard/seed.py` — comment line 592; `write_daytime_artifacts` lines 827-887; caller at 1185.
- `cortex_command/dashboard/templates/feature_cards.html` — lines 39-40 (variable binding), 127-141 (state dl block + primary `pr_url`), **245 (second `pr_url` site in card-link section — additional touch point not in ticket)**. **Adversarial F3**: removing both `pr_url` sites leaves the worktree-interactive path without a PR-url rendering surface — verify #240's plan restored one, otherwise either preserve the rendering (read from a new shape like `feature_pr_url[slug]`) or explicitly accept loss in CHANGELOG.
- `pyproject.toml:32-34` — unregister three console-scripts (`cortex-daytime-dispatch-writer`, `cortex-daytime-pipeline`, `cortex-daytime-result-reader`).
- `justfile` lines **447-559** — `test-dispatch-parity-launchd-real` recipe.
- `.gitignore` **lines 32-34 (not 31-33)** — daytime tempfile patterns.
- `bin/.audit-bare-python-m-allowlist.md` — 4 entries: launchd recipe entry (~lines 22-32) + two `test_daytime_preflight.py` entries (lines 36-48, 50-60).
- `bin/.events-registry.md` line 16 (`dispatch_complete` consumer cite) + **line 119 (not 118)** for `auth_probe` row. Also: the `auth_probe` row's notes column references daytime-pipeline-specific behavior — update notes after consumer-list removal (Adversarial F14).
- `docs/setup.md` lines 121 **and 214** (Agent 1 found a second daytime reference the ticket missed).
- `docs/overnight-operations.md` lines 227, 686, 697, 707-714 — including the "Daytime entry point: deferred-event-emit pattern" subsection at 707-714 (whole sub-section delete).
- `cortex/requirements/observability.md:144` — two module references (`daytime_pipeline`, `daytime_result_reader`). Mechanical catalog update; not a load-bearing requirement.

**NEWLY DISCOVERED touch points (not in ticket):**
- `cortex_command/interactive_lock.py:169` — comment "no worktree removal, no equivalent of daytime's stale-recovery helper" should be reworded.
- `cortex_command/overnight/runner.py:2048` — comment "Parity with daytime_pipeline.py: both paths call resolve_and_probe" becomes a dangling reference. Rewrite to policy-invariant: "Auth path uses ensure_sdk_auth + probe_keychain_presence (single policy)." (Adversarial F11.)
- `skills/lifecycle/references/_interactive_overnight_check.sh:3` — comment references "daytime mirror (implement.md §1a.iii, R8)"; reword to drop §1a.iii reference. (Adversarial F4.)
- `bin/.parity-exceptions.md:22-24` — three `deprecated-pending-removal` rows for the daytime console-scripts. **Must be deleted in same sweep** or parity linter flags missing-source error. (Tradeoffs § E.)
- `docs/internals/sdk.md:7,17` — daytime references in SDK doc.
- `docs/release-process.md:124` — cites #230's filename as canonical release-gate example. **Adversarial F7**: replace with a generic description, do not preserve the dangling reference.

**STRIKE from touch points (already done by siblings #238/#240):**
- `skills/lifecycle/references/implement.md §1 (menu) and §1a (alternate path, 107 lines)` — verified at HEAD `92bbb434`: `grep -i daytime skills/lifecycle/references/implement.md` returns zero matches; §1a is now "Interactive Worktree Creation (Alternate Path)". Replace this touch point with a verification grep as acceptance: `grep -c 'Daytime Dispatch\|cortex-daytime' skills/lifecycle/references/implement.md` = 0.
- `plugins/cortex-core/skills/lifecycle/references/implement.md` — auto-mirror, in sync via pre-commit hook.

**CANCEL — backlog frontmatter (verified states differ):**
- `cortex/backlog/228-wire-daytime-dispatch-through-cli-and-mcp-with-launchd-detachment.md` — current `status: refined`. Cancellation target.
- `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md` — current `status: complete`. **Adversarial F1 caveat**: this has `blocked_by: [228]` which interacts with the cancellation vocabulary choice — see Tradeoffs § C.

### Bidirectional dependency graph (every deleted symbol)

| Symbol / file | Defined at | External consumers | Safe? |
|---|---|---|---|
| `DaytimeResult` / `save_daytime_result` | `state.py:67,517` | Only `daytime_pipeline.py` + `test_daytime_pipeline.py` | ✅ |
| `_DAYTIME_DISPATCH_FIELDS` | `pipeline/metrics.py:335` | `pipeline/metrics.py:422` (same file) + test | ⚠️ See F6 — keep as compat shim |
| `parse_daytime_state` / `parse_daytime_result` | `dashboard/data.py:1365,1374` | Only `dashboard/poller.py` | ✅ |
| `write_daytime_artifacts` | `dashboard/seed.py:827` | Only `dashboard/seed.py:1185` (internal) | ✅ |
| `verify_dispatch_readiness` / `ReadinessResult` (`readiness.py`) | `readiness.py` | `daytime_pipeline.py:42`, `test_dispatch_readiness.py:30`, `test_daytime_pipeline.py:30`, `test_dispatch_parity.py:49` — all being deleted | ✅ |
| Console-scripts `cortex-daytime-*` | `pyproject.toml:32-34` | Justfile recipe (being deleted); operator binstubs in `~/.local/bin/` (orphan after wheel reinstall — see F9/S1) | ⚠️ Needs CHANGELOG note |

### Relevant existing patterns

- **#097 precedent — single-PR atomic removal sweep**: `cortex/lifecycle/archive/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/` explicitly rejected staged PRs because intermediate states are broken. Uses `grep -c` acceptance per requirement. Same shape fits #246.
- **Console-script promotion/demotion**: Phase 3 R13 sweep (`ae685992`) added the three daytime console-scripts. Inverse: remove from `pyproject.toml`, delete `bin/.parity-exceptions.md` rows added at the same time, audit `bin/.audit-bare-python-m-allowlist.md` for orphans.
- **Dual-source drift enforcement**: `.githooks/pre-commit` auto-rebuilds the plugin mirror. No hand-edit needed.
- **CHANGELOG inline `### Removed`**: Verbatim precedent at CHANGELOG.md lines 71-82 (events.log discipline removal), 75 (/fresh,/evolve,/retro retirement), 81 (/discovery auto-scan retirement). Multi-paragraph retirement notes inline; no separate retirement-page convention exists.
- **Supersedence cancellation precedent**: #211 and #212 both use `status: superseded` with body sections titled `## Superseded by #213`. CHANGELOG confirms #213 "Subsumes #212". **However**: neither #211 nor #212 has downstream `blocked_by` chains. #228 does (#230 → blocked_by: [228]). See Adversarial F1.

### Conventions

- Dual-source mirror auto-regenerates via pre-commit hook — do not hand-edit `plugins/cortex-core/skills/lifecycle/references/implement.md`.
- Tests must be deleted in the **same commit** as the modules they import (Adversarial F12 — pytest collection-phase failure if module-import-level references survive across commits).
- TERMINAL_STATUSES extension is its own scope vector — see Tradeoffs § D for the in-PR-vs-defer decision (which is **not** the "punt and don't think about it" answer per Adversarial S2).

## Web Research

### Prior art

- **vulture** (https://github.com/jendrikseipp/vulture) — confidence-thresholded dead-code finder; explicitly fails on dynamic dispatch, entry points, decorators. Manual grep needed for the blind spots.
- **deadcode** (EuroPython 2024, https://ep2024.europython.eu/session/deadcode-a-tool-to-find-and-fix-unused-dead-python-code/) — successor with `--fix`; same blind spots on string-keyed dispatch and entry points.
- **Michael Nygard ADR template** (https://github.com/joelparkerhenderson/architecture-decision-record/) — canonical four statuses: Proposed / Accepted / Deprecated / **Superseded by ADR-NNNN**. Treats `Deprecated` and `Superseded` as semantically distinct.
- **Shopware ADR supersession** (https://developer.shopware.com/docs/resources/references/adr/) — uses an `adr/_superseded/` directory pattern for archival.
- **WordPress Trac vocabulary proposal** (https://make.wordpress.org/core/2020/06/24/proposal-rename-invalid-worksforme-and-wontfix-ticket-resolutions/) — proposes adding `fixed-elsewhere`/`outdated`/`superseded` to disambiguate from `wontfix`. Validates the missing-vocabulary problem is real and recurring.
- **uv tools docs** (https://docs.astral.sh/uv/concepts/tools/) — confirms `[project.scripts]` changes require reinstall, but is silent on orphan-binstub cleanup. The clean path is `uv tool uninstall && uv tool install`, **not** `uv tool install --reinstall`.
- **pytest Deprecations and Removals** (https://docs.pytest.org/en/stable/deprecations.html) — 3-field shape (what removed / what replaces / removed-in version) inline with CHANGELOG.

### Forgotten-reference categories during dead-code sweeps

vulture/static analysis cannot see: (1) entry points in `[project.scripts]`, (2) string-keyed dispatch tables, (3) docstrings + Sphinx xrefs, (4) argparse help text + error messages, (5) test fixtures and conftest imports, (6) hook config / settings JSON, (7) CHANGELOG / release-note backlinks. Manual grep is the only reliable check.

### Anti-patterns

- **Deleting modules before tests** → broken import in test suite that may not run until CI. Convention: **delete tests first, then modules** (matches deadcode's iterative-rerun guidance).
- **`git rm` without CHANGELOG entry** → loses "why removed" context. Git log shows the commit, not the rationale.
- **`wontfix` for completed-elsewhere work** → conflates "we won't" with "yes, but elsewhere." Trac discussion and Nygard ADR template explicitly distinguish these.

### Cancellation-vocabulary convention (Nygard ADR + Trac converge)

- `wontfix` = "we decided not to do this" (rejection)
- `abandoned` = "started and stopped mid-flight" (incomplete)
- `duplicate` = "exact same issue, see other ticket"
- `superseded` = "work was completed by a different ticket/approach" — **semantically distinct from the three above**

Industry convention supports a dedicated `superseded` status. #246's choice intersects with **TERMINAL_STATUSES extension** and **downstream blocker-check behavior** — see Tradeoffs § C and Adversarial F1.

## Requirements & Constraints

**`cortex/requirements/project.md`** (load-bearing):
- L9-11 day/night split — daytime is interactive, autonomous daytime SDK pipeline is the inverse; removal aligns.
- L19 "Complexity must earn its place" + L43 "Maintainability through simplicity: Complexity is managed by iteratively trimming skills/workflows."
- L21 Solution horizon / current-knowledge test.
- L46 Destructive ops preserve uncommitted state — does NOT apply to repo-internal source artifact deletes; bears only on user-visible runtime artifacts (worktrees, branches, sessions). Not blocking.
- **L86 "Workflow trimming: unearned workflows are removed wholesale. Retirements in `CHANGELOG.md`"** — binding directive. This PR MUST add a CHANGELOG `### Removed` entry. CHANGELOG already has precedent for multi-paragraph inline retirement entries (e.g., `/fresh,/evolve,/retro` at line 75).

**`cortex/requirements/multi-agent.md`**:
- No daytime references. Worktree Isolation governs overnight worktrees only; no daytime-coupled requirement.
- **L49** codifies that overnight orchestrator reads `intra_session_blocked_by` (from `blocked_by` frontmatter) at round-planning time. The ticket's sequencing assumption (#238/#240 must merge first) is mechanically supported.

**`cortex/requirements/observability.md:144`**:
- Catalog entry under "Install-mutation invocations" section (lines 122-147). Both daytime modules classified as "Non-install-mutation (no guard call needed)." **Mechanical reference update, not a requirements conflict.**

**`cortex/requirements/pipeline.md`**:
- No daytime references. The "behavioral overnight untouched" claim is grounded in code-evidence (grep), not requirements invariant. Pipeline.md's Session Orchestration acceptance criteria function as de facto behavioral baseline.

**`cortex_command/common.py:162-170` TERMINAL_STATUSES frozenset**: `{complete, abandoned, done, resolved, wontfix, won't-do, wont-do}`. Does NOT include `superseded`. NOTE at L159 flags a second tuple at `cortex_command/overnight/backlog.py:40` — unification flagged as follow-up.

**Architectural constraints applying to this PR**:
- Console-script removal contract (`project.md:35`).
- Events registry update required (`project.md:35,38`): `bin/.events-registry.md:119` `auth_probe` consumer column must be updated.
- SKILL.md-to-bin parity enforcement (`project.md:33`): `bin/cortex-check-parity` covers `skills/lifecycle/SKILL.md` references; mirror auto-sync.
- TERMINAL_STATUSES vocabulary decision (see Tradeoffs § C and § D).

**Scope boundaries**:
- In Scope: AI workflow orchestration (skills, lifecycle, pipeline); overnight execution framework.
- Out of Scope: dotfiles, application code, packaged libraries for others — not touched.
- Optional (prunable but binding when present): workflow-trimming retirement directive at `project.md:86`.

## Tradeoffs & Alternatives

### A. PR shape

- **A1 single atomic PR** ✅ recommended. Matches #097 precedent which explicitly rejected staging because intermediate states (modules deleted but tests not, or vice versa) are reachable and broken. One mergebase for revert; coherent supersedence story.
- A2 staged 4-PR — multiplies plan/spec/review overhead; orphans cancellation rationale if delayed.
- A3 two-PR code/docs split — no in-repo precedent; the cleavage along compile-vs-grep boundary is theoretically clean but adds coordination overhead.

**Adversarial S3 refinement**: even within A1, use **sequenced commits** along F12's boundary so each commit is independently runnable: (1) tests + console-scripts + modules together (single commit per F12 — collection-phase safety); (2) dashboard cleanup; (3) docs/registries cleanup; (4) backlog cancellation. All four commits in one PR; bisect-safe.

### B. `readiness.py` handling

- **B1 delete `readiness.py` + delete full `test_dispatch_readiness.py`** ✅ recommended. Spec, discovery RQ4, and #097 pattern all agree. Bidirectional grep confirms no surviving non-test, non-daytime importer.
- B2 preserve `readiness.py` — speculative future-reuse without a named caller; conflicts with solution-horizon principle.
- B3 delete + rewrite tests for worktree-interactive sibling — out of scope (belongs to #238/#240's territory).

### C. Cancellation vocabulary (LOAD-BEARING)

The choice intersects three constraints: (i) `cortex/backlog/{211,212}-*.md` precedent uses `status: superseded` (no downstream blockers); (ii) `cortex_command/common.py:162-170` TERMINAL_STATUSES does NOT include `superseded`; (iii) #228 has a downstream blocker (#230) and is in flight; #230 is already `status: complete` with `blocked_by: [228]`.

**Critical adversarial finding (F1)**: `cortex_command/backlog/readiness.py:154` filters blocker status via `if resolved_status not in TERMINAL_STATUSES: non_terminal_internal.append(...)`. So if #228 is marked `status: superseded` (not in TERMINAL_STATUSES), the readiness gate treats #230 as "blocked by 228: superseded" indefinitely. Today #230 is already `complete` so this doesn't bite. But the same problem would affect any future `blocked_by: [228]` chain. And **the symmetric problem applies if someone in the future marks anything `blocked_by: [#228, #246]` and #246 itself gets superseded** — the chain propagates the issue.

**The "defer TERMINAL_STATUSES extension to follow-up" answer (Tradeoffs § D2) is broken** when paired with `superseded` for #228 — it leaves the vocabulary in a state where the new status string is neither eligible nor terminal. (Adversarial S2.)

Options that actually resolve the conflict:

- **C1 — Use `status: superseded` for #228 AND add `superseded` to TERMINAL_STATUSES in this PR**. Matches industry convention (Nygard ADR + Trac), matches #211/#212 precedent, fixes the blocker-check problem. Cost: one-line addition to `common.py:162` frozenset + `normalize_status` map at L769-778 + test assertion. Out-of-scope creep is minimal (single-line change).
- **C2 — Use `status: wontfix` for #228**. Canonical TERMINAL_STATUSES member, no blocker-check issue. Cost: misaligned with #211/#212 precedent and external convention; loses the semantically-correct supersedence vocabulary.
- **C3 — Split: `superseded` for #228 + leave #230 `complete` with body annotation, defer TERMINAL_STATUSES** ❌ original recommendation now rejected per F1. The "defer" half breaks downstream readers.

**Revised recommendation: C1**. The TERMINAL_STATUSES addition is small enough that it does not constitute scope creep — it's the necessary co-edit for the supersedence vocabulary choice. Pair it with a separate follow-up ticket for the larger work of unifying the second tuple at `cortex_command/overnight/backlog.py:40`.

For #230 specifically: leave `status: complete` intact (the release-gate fired or didn't fire — real history). Append a body section noting "Parent ticket #228 cancelled via #246; release-gate procedure no longer applies." Do not downgrade `complete` → `superseded` — that rewrites history.

### D. TERMINAL_STATUSES extension scope

- **D1 — Add `superseded` to TERMINAL_STATUSES in this PR (paired with C1)** ✅ recommended. Necessary co-edit for the cancellation vocabulary; one-line frozenset addition + one-line normalize_status + test assertion. Does not unify the second tuple in `overnight/backlog.py:40` — that's its own follow-up.
- D2 — Defer entirely — broken per Adversarial S2 (leaves `superseded` as neither eligible nor terminal).

### E. Console-script unregistration ritual

- **E2 — pyproject + `bin/.parity-exceptions.md:22-24` row deletion + CHANGELOG migration note** ✅ recommended. The parity-exceptions rows exist precisely as the deferred-deletion record for these scripts; they must die with the scripts. CHANGELOG migration note must say `uv tool uninstall cortex-command && uv tool install ...` explicitly (NOT `--reinstall` — Adversarial F9/S1/A3).
- E1 minimal — leaves parity-exceptions rows orphaned; parity linter would flag missing-source.
- E3 + cleanup script — over-engineered; no in-repo precedent for binstub-scrub-on-init.

### F. CHANGELOG retirement shape

- **F1 — Inline `### Removed` entry in [Unreleased]** ✅ recommended. Verbatim precedent in CHANGELOG.md at lines 71-82 and 75 (`/fresh,/evolve,/retro` is the closest precedent for a multi-paragraph retirement with operator-action notes).
- F2 separate retirement page — no precedent.

### G. implement.md touch-point handling (LOAD-BEARING)

- **G1 — Strike `implement.md §1 and §1a` from touch points; replace with verification grep** ✅ recommended. The siblings #238/#240 already did this work at HEAD `92bbb434`. Touch-points list should reflect what this PR actually changes. **Adversarial F15 caveat**: add a structural test pinning `"cortex-daytime" not in skills/lifecycle/references/implement.md` to convert the assumption into an invariant — protects against sibling-PR revert.
- G2 keep as verification — adds confusion (touch point with expected zero diff).
- G3 minimal touch — same as G2.

### H. `_DAYTIME_DISPATCH_FIELDS` metrics filter (LOAD-BEARING, NEW from adversarial)

**Adversarial F6 reframe**: this is NOT dead code post-removal. It is a **read-side compatibility shim** that prevents archived daytime-schema rows in users' historical `pipeline-events.log` files from contaminating overnight metric aggregation. The writer (daytime_pipeline.py) is gone, but the reader (`pipeline/metrics.py`) continues to encounter daytime rows in archived logs.

- **H1 — Keep the filter, retitle the docstring** ✅ recommended. Change docstring to "Historical compatibility — skip pre-#246 daytime-schema rows in archived event logs." Keep the test (`test_daytime_schema_skipped`). This is graveyard-prose-as-compat-shim, semantically distinct from dead code.
- H2 — Delete the filter per ticket — contaminates historical metric aggregation on every user machine with archived daytime events.

### I. Order-of-operations within the PR (NEW from adversarial F12)

Even within A1's single PR, in-commit sequence matters for `git bisect`:

- Commit 1 (modules + tests + console-scripts together): tests deleted, modules deleted, `pyproject.toml` scripts removed, `bin/.parity-exceptions.md` rows removed. Single commit because partial states fail pytest collection.
- Commit 2: dashboard cleanup (data.py, poller.py, seed.py, feature_cards.html).
- Commit 3: docs + registries + .gitignore + audit allowlist + observability.md + auth.py docstrings + cli_handler.py xref + runner.py:2048 comment + interactive_lock.py:169 comment + _interactive_overnight_check.sh:3 comment.
- Commit 4: backlog cancellation (#228 status: superseded + body; #230 body annotation), CHANGELOG `### Removed` entry, TERMINAL_STATUSES + normalize_status edits + test, structural-pin tests for implement.md.

Each commit's `just test` passes. Bisect-safe.

### Recommended scope shape

#246 lands as **a single atomic PR with four sequenced commits** modeled on #097 + Adversarial F12 ordering. Includes:

- Module + test + console-script deletion in one commit (collection-safe).
- `readiness.py` deleted + `test_dispatch_readiness.py` deleted in full (Tradeoffs B1).
- Dashboard surface trim in a second commit.
- Docs + registries + code-hygiene + comment cleanup in a third commit, including newly-discovered sites: `runner.py:2048`, `_interactive_overnight_check.sh:3`, `interactive_lock.py:169`, `auth.py:553` argparse, `docs/release-process.md:124` citation, `docs/setup.md:214`, `docs/internals/sdk.md:7,17`, `bin/.parity-exceptions.md:22-24`.
- `_DAYTIME_DISPATCH_FIELDS` filter and test **kept** as a read-side compat shim (H1) — docstring retitled.
- Backlog cancellation in a fourth commit: #228 → `status: superseded` + body section; #230 → leave `complete`, append body annotation. TERMINAL_STATUSES + normalize_status edits + test assertion. CHANGELOG `### Removed` entry with operator-action note for `uv tool uninstall && uv tool install`. Structural-pin test for `implement.md` (no `cortex-daytime` token).
- **Strike** `skills/lifecycle/references/implement.md §1, §1a` from touch points (already done by siblings) — replaced with a verification grep + structural test.

**Load-bearing decisions** (must be reviewed before merge): A1 atomic-PR shape, B1 readiness.py full deletion, **C1 `superseded` for #228 + TERMINAL_STATUSES extension in this PR**, E2 binstub-cache CHANGELOG note, G1 implement.md touch-point amendment, **H1 keep `_DAYTIME_DISPATCH_FIELDS` filter as compat shim**.

**Cosmetic decisions**: F1 inline-Removed CHANGELOG shape.

**Out-of-scope follow-ups to file when #246 lands**: unify the second TERMINAL_STATUSES tuple at `cortex_command/overnight/backlog.py:40`; remediate dashboard PR-url rendering for worktree-interactive features (Adversarial F3) if #240's plan didn't already.

## Adversarial Review

### Top 3 biggest risks (must mitigate before merge)

1. **F1 — `status: superseded` for #228 silently breaks blocker-check for any `blocked_by: [228]` chain.** `cortex_command/backlog/readiness.py:154` treats non-TERMINAL_STATUSES blockers as non-terminal. The Tradeoffs § C3 original recommendation (defer TERMINAL_STATUSES extension) leaves the vocabulary broken. **Resolution: C1 — add `superseded` to TERMINAL_STATUSES in this PR.**
2. **F6 — `_DAYTIME_DISPATCH_FIELDS` metrics filter is a read-side compatibility shim, NOT dead code.** Archived `pipeline-events.log` rows on users' machines still contain daytime-schema entries. Deleting the filter contaminates historical metric aggregation. **Resolution: H1 — keep filter, retitle docstring.**
3. **F9 + S1 — Orphan binstubs persist after `uv tool install --reinstall`.** Stale `~/.local/bin/cortex-daytime-*` binstubs remain executable until `uv tool uninstall && uv tool install`. **Resolution: CHANGELOG migration note MUST say `uv tool uninstall cortex-command && uv tool install git+<url>@<latest-tag>` explicitly.**

### Other failure modes

- **F2** `auth.py:553` argparse `description=` embeds "daytime_pipeline.py" — vulture-blind. Rewrite description to "Resolve the SDK auth vector for the overnight runner."
- **F3** Dashboard `feature_cards.html:141,245` are the only `pr_url` rendering sites for daytime. With daytime removed, the worktree-interactive path has no PR-url rendering unless #240 already restored one. Verify or accept loss in CHANGELOG.
- **F4** `_interactive_overnight_check.sh:3` comment references "daytime mirror (implement.md §1a.iii)" — dangling reference; add to touch points.
- **F5** `test_dispatch_readiness.py` partial-delete (per ticket text) is structurally impossible; spec must say "delete entire file."
- **F7** `docs/release-process.md:124` cites #230 as canonical release-gate example. Replace with generic description.
- **F8** `.github/workflows/auto-release.yml` triggers on push to main with `pyproject.toml`/`CHANGELOG.md` changes. Coordinate merge window with other sweep PRs.
- **F10** Smoke-test gap: #240's plan provides per-task coverage but no single end-to-end smoke test equivalent to deleted `test_daytime_preflight.py` (407 lines of contract + double-dispatch + overnight-concurrent guards). Add one structural contract test in this PR for the implement-option-2 dispatch.
- **F11** `runner.py:2048` "Parity with daytime_pipeline.py" comment becomes dangling. Rewrite to policy-invariant.
- **F12** Pytest collection-phase fails if module-import-level references in test files survive across commits where the modules are deleted. Forces tests + modules + console-scripts into one commit.
- **F13** Dual-source mirror pre-commit hook requires `plugins/cortex-core/skills/lifecycle/references/implement.md` to stay in sync. Add `just check-parity` to PR verification.
- **F14** `bin/.events-registry.md:119` `auth_probe` row's notes column has daytime-specific wording — update notes after consumer-list removal.
- **F15** "implement.md already done" is true at HEAD but not pinned by a test. Add structural-pin test.

### Security / anti-patterns

- **S1** Orphan binstub execution surface — see F9 mitigation.
- **S2** `superseded` deferred to follow-up is the worst-of-both-worlds answer. Resolve in this PR.
- **S3** 30+ path PR: mitigate via sequenced commits within one PR per § I.

### Assumptions validated by research

- "behavioral overnight untouched" — confirmed via bidirectional grep (no production overnight consumer of any deleted symbol).
- "blocked-by sequencing works at round-planning" — confirmed via `cortex_command/overnight/backlog.py:91,328,370` + `multi-agent.md:49`.
- "implement.md edits already done" — confirmed via grep against HEAD `92bbb434`. (Add structural pin per F15.)

## Open Questions

1. **#240's PR-url rendering surface for worktree-interactive features** — Adversarial F3 flagged that removing `feature_cards.html:141,245` leaves the new path without a PR-url render site. **Deferred**: needs verification against #240's plan before deletion; if #240 did not restore it, the spec must add it or accept loss in CHANGELOG.
2. **Auto-release coordination window** — Adversarial F8 flagged that `auto-release.yml` triggers on push to main with `pyproject.toml`/`CHANGELOG.md` changes. **Deferred**: will be resolved at merge time by coordinating with the operator (not at spec time).
3. **#230's frontmatter — leave `complete` or downgrade to `superseded`?** — Tradeoffs § C and Agent 4's discussion converged on leaving `complete` intact with a body annotation. **Resolved**: leave `status: complete`; append body section. The release-gate-procedure-moot annotation is real history, not retroactive supersession.
4. **`superseded` added to TERMINAL_STATUSES in this PR vs deferred?** — Adversarial F1 + Tradeoffs § C revision converge on adding it now (option C1). **Resolved**: add in this PR. The unification work for the second tuple at `overnight/backlog.py:40` is a separate follow-up.
5. **Smoke-test contract test for implement-option-2 in this PR?** — Adversarial F10 recommends one structural contract test. **Deferred**: defer to spec phase as a §4 Q&A item — the user should choose whether to include the additional contract test in this sweep or split it to its own ticket.

## Considerations Addressed

- **Re-verify the blast-radius inventory bidirectionally** — Addressed. Agent 1 + Agent 3 confirmed `readiness.py` is a true leaf (no non-test, non-daytime importer); `DaytimeResult` / `save_daytime_result` / `_DAYTIME_DISPATCH_FIELDS` / dashboard daytime helpers have no surviving consumers. **However**, Adversarial F6 reframed `_DAYTIME_DISPATCH_FIELDS` as a read-side compat shim (not dead code), and `test_dispatch_readiness.py` partial-delete is impossible. Recommendation: delete the file in full + keep the metrics filter.
- **Reconcile off-by-one between Role prose and Touch points** — Addressed. On-disk inventory confirms 5 `test_daytime_*.py` files + 1 `test_dispatch_parity.py` = 6 total daytime-related test files. The "six daytime test files plus the dispatch-parity test" Role prose is off by one against the Touch-points enumeration (which lists 5 + 1). Touch points are authoritative; flag the Role prose typo when writing the spec.
- **Confirm canonical backlog status vocabulary for cancellation/supersedence** — Addressed. Industry convention (Nygard ADR, Shopware, WordPress Trac discussion) treats `superseded` as semantically distinct from `wontfix`/`abandoned`. #211/#212 use it de facto. Recommendation revised by Adversarial F1: use `status: superseded` for #228 **and** add `superseded` to TERMINAL_STATUSES in this PR (option C1) — the "defer to follow-up" answer breaks the blocker-check at `readiness.py:154`.
- **Smoke-test gate via #240's coverage** — Partially addressed. Agent 1 + Agent 3 confirmed `multi-agent.md:49` codifies the blocked-by sequencing at round-planning. Adversarial F10 caveat: #240 provides per-task coverage but no single end-to-end smoke surface equivalent to deleted `test_daytime_preflight.py` (407 lines). Open question 5 carries this to spec.
- **Sequencing assumption (#238/#240 must merge first)** — Addressed. Mechanically supported by `cortex_command/overnight/backlog.py:91,328,370-371` + `multi-agent.md:49` filter at round-planning time. Both sibling tickets are `status: refined` and in active lifecycles; the implement.md edits are already at HEAD `92bbb434`. Recommendation: strike implement.md touch points (G1) and add a structural pin test (F15).
