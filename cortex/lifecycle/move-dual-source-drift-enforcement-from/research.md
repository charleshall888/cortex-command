# Research: Repair the dual-source drift gate's comparand

**Clarified intent (as researched).** The `.githooks/pre-commit` Phase 4 drift loop compares the working tree against the index, so a concurrent session's unrelated uncommitted edits block an unrelated commit. Research was dispatched on the premise that the fix was to delete Phase 4 and relocate enforcement to CI. **That premise did not survive.** The adversarial angle reproduced (and the orchestrator independently confirmed) that Phase 4 is also the only mechanism that gets rebuilt mirrors *into* a commit — so deleting it does not relocate enforcement, it ends mirror maintenance. The design settled on is a root-cause repair of the comparand, in place, with no CI step.

> **Note on scope drift.** The backlog ticket #418 (`Move dual-source drift enforcement from the commit gate to the release gate`) describes a design this research disproved. Its title, Why, Role, Integration, Edges, and Touch points all need rewriting; the lifecycle slug `move-dual-source-drift-enforcement-from` is retained as the stable identity key regardless.

---

## Codebase

### `.githooks/pre-commit` phase map

583 lines, `#!/bin/bash` with `set -euo pipefail` (`:1,24`), runs from repo root (`:26-27`). The header docstring (`:1-22`) claims "five phases" and is already stale — the code carries thirteen numbered sub-phases (1, 1.5, 1.55, 1.6, 1.7, 1.86, 1.87, 1.95, 1.96, 1.97, 2, 3, 4).

- **Phase 1 — classification guard** (`:29-68`): populates `BO` (`:35-38`, from `just _list-build-output-plugins`) and `HM` (`:39-42`); validates a non-empty `.name` in every `plugins/*/.claude-plugin/plugin.json` (`:49-52`); fail-closes on a plugin dir in neither list (`:54-66`).
- **Phases 1.5–1.97** (`:70-519`): independent staged-path-triggered gates (sandbox preflight, contract linter, bin shim check, telemetry entry-point, bare-python-import scan, skill-path scan, `install_guard` parity, `cli_pin.py` AST check, `install_core.py` stdlib/parity). None reference `BO`, `HM`, `drift_found`, or `drift_report`.
- **Phase 2 — build decision** (`:522-540`): `staged` from `git diff --cached --name-only --diff-filter=ACMR` (`:525`); sets `BUILD_NEEDED=1` on `^(skills/|bin/cortex-|hooks/cortex-|claude/hooks/cortex-)` (`:528-530`) or any `plugins/$p/` build-output path (`:532-540`).
- **Phase 3 — conditional build** (`:542-551`): runs `just build-plugin`, exits 1 on failure. Invoked with `>/dev/null 2>&1` (`:546`).
- **Phase 4 — drift loop** (`:553-581`): iterates `BO`, skips plugins absent from disk and index (`:561-563`), runs `git diff --quiet -- "plugins/$p/"` (`:564`), accumulates `drift_report`, exits 1 (`:573-581`). `drift_found`/`drift_report` are used nowhere else.

### `.github/workflows/validate.yml`

`on: push` and `on: pull_request`, no path or branch filters (`:3-5`). Single `validate` job on `ubuntu-latest`. Runner has `actions/checkout@v4`, Python 3.12, `pip install pyyaml pytest` (`:11-20`). **No workflow in this repo installs or invokes `just`** — verified, `grep` across `.github/workflows/` returns nothing.

Every blocking step carries `if: ${{ !cancelled() }}`; the comment at `:22-26` records why — without it Actions aborts at the first failure and marks later steps `skipped`, "which is how four blocking steps went unexecuted for days behind one red test (#386)."

### `justfile` `build-plugin`

Recipe at `:609-648`; constants at `:595-596`; list helpers at `:598-606`.

- `rsync -a --delete "skills/$s/" "plugins/$p/skills/$s/"` per skill (`:636-638`) — `--delete`, so canonical deletions propagate.
- `rm -f plugins/$p/hooks/cortex-*.sh` then per-hook `rsync -a` (`:639-644`).
- `rsync -a --delete --include='cortex-*' --exclude='*' bin/ "plugins/$p/bin/"` (`:645-647`), `cortex-core` only.

Needs only `rsync` and bash. Writes exclusively under `plugins/$p/`; reads from `skills/`, `hooks/`, `claude/hooks/`, `bin/`. Runs in ~0.5s.

### `git status --porcelain` vs `git diff --exit-code` (empirically verified)

| Scenario | `git status --porcelain -- plugins/` | `git diff --exit-code -- plugins/` |
|---|---|---|
| tracked mirror modified | flags (` M`) | flags (exit 1) |
| **new canonical file → untracked mirror** | **flags (`??`)** | **MISSES (exit 0)** |
| canonical deleted → `--delete` removes mirror | flags (` D`) | flags |
| hand-edit to a mirror | flags | flags |
| new never-materialized plugin dir | flags (`??`) | MISSES |

`git status --porcelain` **always exits 0** regardless of dirty state, so any check must gate on output *content* (`test -z "$(...)"`), never on exit code. `.gitignore` carries one entry under `plugins/` (`plugins/cortex-pr-review/skills/pr-review/.cache/`, `.gitignore:15`) — a hand-maintained plugin `build-plugin` never touches, so harmless today.

### Consumers of the files in scope

- Both parity tests are reachable only via `just test`'s blanket `pytest tests/ -q` (`justfile:543`), never by name from any workflow or recipe.
- `tests/test_drift_enforcement.sh` is reachable by **zero** automated paths — `pytest tests/ -q` collects only `test_*.py`, and no recipe or workflow invokes it. Manual-only.
- Nothing outside the hook references `drift_found`, `drift_report`, or `git diff --quiet -- plugins/`.

### Existing regenerate-and-verify idiom

The repo's established pattern is **in-memory regeneration compared byte-wise inside pytest**, not a filesystem/git-level check: `tests/test_lifecycle_kept_pauses_parity.py` imports `generate_md` and compares against the committed file, CI-wired at `validate.yml:49-51`. `just sync-install-guard --check` is shell-level but pre-commit-only. No CI step currently does "run a generator, then diff the working tree."

---

## Web & Prior Art

### The canonical CI idiom

Two families. **Tool-native check mode** (`terraform fmt -check`, `cargo fmt --check`) — unavailable for an rsync mirror. **Regenerate-then-diff-against-git** — the relevant one:

- `connectrpc/connect-rust` issue #95 proposes `task generate:all` followed by `git diff --exit-code <paths>`, modeled on live jobs in `anthropics/buffa`'s `.github/workflows/ci.yml` (`check-changelog`, `check-generated-code`).
- **Kubernetes is the field-tested reference**: `hack/lib/verify-generated.sh` creates an isolated `git worktree add -f -q "${_tmpdir}" HEAD`, runs the generator inside it, then counts `diffs=$(git status --porcelain | wc -l)` — explicitly using porcelain, not `git diff`, and reporting via both `git status` and `git diff`.

**The untracked-file gap is real and widespread.** `nickcharlton/diff-check`'s implementation is `git diff --quiet HEAD`, blind to new files by construction. Mature projects close it with `git status --porcelain`, or `git add -A -- <path> && git diff --cached --exit-code -- <path>`.

### Diagnosability in Actions

GitHub's default `run:` shell is `bash --noprofile --norc -eo pipefail {0}` — `-e` is on. A bare `git diff --exit-code` aborts the block before any following `echo` runs; the fix every real example uses is `if ! <check>; then <diagnostics>; exit 1; fi` (a command in an `if` condition is exempt from `-e`). `$GITHUB_STEP_SUMMARY` accepts Markdown, 1 MiB/step, 20 summaries/job; `diff-check`'s action pipes through `tee -a` so output reaches both the summary and the job log.

### `just` on a runner

`extractions/setup-just@v4` (maintained, last push 2026-06-24) or `taiki-e/install-action@v2` with `tool: just` (adds SHA-256 verification). `rsync 3.2.7-1ubuntu1.5` is preinstalled on the Ubuntu 24.04 image `ubuntu-latest` resolves to. *(Not used in the chosen design — recorded for the deferred CI option.)*

### Committed generated artifacts

Mitigations, since the mirrors must stay committed: `.gitattributes` `linguist-generated` (collapses the GitHub PR diff, cosmetic only); `-diff` (git treats as binary, suppresses line-level diff); `merge=ours` — **note the trap**: merge-driver definitions live in `.git/config`, not the tracked `.gitattributes`, so they are not shared by cloning and are silently a no-op on every fresh clone and CI runner unless registered.

### Pre-commit vs pre-push vs CI

The working-tree-vs-index problem is well documented. The textbook fix — `git stash --keep-index` around the checks — carries a **documented data-loss failure mode**: `pre-commit/pre-commit#176` records unstaged work destroyed outright when `git apply` failed on `stash pop` (rc 128, stash never restored). Open issues #2803 and #1870 ask to make stashing optional for this reason.

Prior art converges on a three-tier split — editor, fast local hook, CI as enforcement authority — but **that convergence assumes CI can block a merge**. Also: a pre-push hook still runs against the working tree, so it inherits the same false-positive class at a less frequent trigger point. It is not a fix.

---

## Requirements & Constraints

### "Enforcement gates carry named evidence" (`cortex/requirements/project.md:41`)

> "a pre-commit/CI gate survives only by naming the specific, evidenced failure it prevents. Per-gate disposition landed 2026-07-21 (#407). Survivors and their evidence: … A new gate enters only with its named failure stated here."

**The dual-source drift gate appears in neither the survivors list nor the retired list** — #407's disposition pass never covered it. The rule is gate-shape-agnostic ("pre-commit/CI"), so relocation grants no exemption, and there is no existing entry to relocate. Any change here must add a ledger entry stating the gate's disposition and evidence.

### "Deletion bias" (`:23`)

> "Keeps, safeguards, and measurement tooling must clear the same evidence bar as new features — named, specific evidence, not hypotheticals; when a trim is proposed, the burden of proof sits on keeping, not deleting… a ticket adding harness machinery names its specific evidence in its Why."

Applies symmetrically: the removal side is default-favored; the addition side (any new CI gate) must name evidenced failure.

### `CLAUDE.md`

- `:18` — "canonical source mirrored into the `cortex-core` plugin's `bin/` via dual-source enforcement". Remains true.
- `:22` — "Run `just setup-githooks` after clone to enable the dual-source drift pre-commit hook." Remains true under the chosen repair (the hook still enforces drift).
- `:28` — "the `plugins/cortex-core/{skills,hooks,bin}/` mirrors regenerate via the pre-commit hook." Remains true, and under the chosen design becomes *more* true (the hook now also stages them). The ticket cites this as `:27`; it is at `:28`.
- The change's own files (`.githooks/`, `tests/`, `.github/workflows/`) are **not** in `:28`'s lifecycle-gated path list.

### `docs/policies.md`

`:11` elaborates "prefer structural separation over prose-only enforcement for sequential gates" — bears directly on the rejected delete-both option, which would convert a structural gate into prose. `:17` states the dual-source mechanism generally. **No ownership map covers `docs/plugin-development.md`** (`:37-39` and `:41-43` own only the overnight and lifecycle served-loop doc sets), so nothing forces it to stay in sync with the hook's actual behavior.

### `docs/plugin-development.md`

Passages describing drift behavior: `:22-24` (Phase 1 classification — survives), `:34-43` (§ "Setting up the dual-source drift hook", "four conceptual phases"), `:72-91` (§ "Drift detection and the pre-commit hook" incl. the numbered phase list), `:93-102` (§ "Fixing a drift failure"), `:106-108`, `:126`, `:133-135`. Under the chosen repair most survive in substance but need accuracy edits: the phase count, the description of what Phase 4 compares, and the "Fixing a drift failure" remediation (which becomes largely automatic). The sub-phase list at `:43` is already wrong independently of this change.

### `cortex/adr/`

No ADR covers the dual-source drift mechanism. Tangential: ADR-0009 (`:29`) cites "a new dual-source drift surface" as a cost in a *rejected* alternative; ADR-0026 (`:130`) references the distinct Phase 1.97 parity gate; ADR-0017 (`:55,73,75`) covers a separate `lifecycle-config.md` asset↔mirror gate. ADR-0002 establishes the wheel+plugin distribution model but not drift enforcement.

**Three-criteria gate** (`cortex/adr/README.md:19-27`) requires all of: hard to reverse, surprising without context, result of a real trade-off. `README:23` states "A decision that can be unwound by editing one file in one PR does not clear this bar." **No ADR is required for this change.**

### Scope boundaries

No area doc matches tags `harness`/`git-hooks`/`ci` or area `tooling`; the Conditional Loading map (`project.md:93-100`) has no entry routing hook/CI topics. Governed solely by `project.md` and `CLAUDE.md`.

---

## Tradeoffs & Alternatives

### Root cause

Not "`git diff` is the wrong comparison" alone, but a composition: Phase 3 rsyncs `plugins/` from **whatever is on disk** across the whole working tree — not just this commit's files — and Phase 4 then compares that against the index, which under `--only` is HEAD-plus-pathspec. Both observed false positives involved two Claude Code sessions **sharing one physical working directory** (not isolated worktrees — otherwise Phase 3 could not have seen the sibling's files at all).

### Repairing by scoping the diff to staged-derived paths

Implementable in ~40-60 lines: collect `git diff --cached --name-only`; map `skills/<name>/**` to its owning plugin; map `bin/cortex-*` to `cortex-core`; map hooks paths (noting `hooks/cortex-cleanup-session.sh` and `hooks/cortex-cli-background-install.sh` fan out to **both** `cortex-core` and `cortex-overnight`); include directly-staged `plugins/**`; diff only the derived set. Eliminates both observed false positives. **Cost:** the skill→plugin mapping exists in exactly one place — the inline `case "$p" in` block at `justfile:615-635` — so this needs either a hand-copied third copy or a justfile refactor to externalize it.

### `git stash --keep-index` — unsafe here

Two sessions demonstrably share one working tree. `git stash` operates on that shared tree: running it inside session A's hook forcibly removes session B's in-progress edits from disk while B's agent may be actively writing them. Combined with the documented `pre-commit#176` data-loss mode, this trades one race for a worse one. **Rejected.**

### Removing the dual-source problem at the root

- **Generate at release time** — foreclosed. Marketplace resolves `./plugins/<name>` against a git checkout with no build step; `docs/setup.md:70` warns the URL form "silently breaks plugin installs" for exactly this reason. Something must be committed.
- **Symlinks** — the mapping is a clean partition (11 + 2 + 1 = 14 skill dirs, matching `ls skills/` exactly, no name repeated; `bin/cortex-*` → `cortex-core` only). Fan-out on two hook files is fine for symlinks. The blocker is whether Claude Code's plugin loader follows a symlink resolving *outside* the plugin's declared root — plausible as a path-traversal refusal, unverified. Migration also inverts the canonical-source direction assumed by `CLAUDE.md`, ADR-0009, `cortex-check-skill-path`, and the contract linter. **Deferred to a narrowly-scoped spike, not this ticket.**
- **Self-healing bot commit** — rejected; adds a second PAT-authenticated write path with its own race and self-retrigger concerns for a rare, understood bug.

### CI cost and the `just` precedent

`cortex/lifecycle/wire-cortex-check-contract-into-ci/spec.md:20` (#283, shipped, all tasks done) Requirement 5: **"No wheel / no `just`/`uv` install added"**, with acceptance `grep -Ec 'uv tool install|pip install +git\+|cortex-command@|setup-just' .github/workflows/validate.yml` = 0. **Verified: currently returns 0.** Adding `setup-just` would literally break a shipped acceptance criterion. `:50` records the deliberate deviation this forced last time (CI invokes the binstub directly rather than via `just`).

### The three-mechanism question

- **Phase 4** covers the full `build-plugin` scope: `skills/`, `bin/cortex-*`, both hooks lists.
- **`tests/test_dual_source_reference_parity.py`** — glob over `skills/*/SKILL.md`, `references/*.md`, `assets/*.md`, routed via a hand-maintained `PLUGINS` dict. Skills-only; never touches `bin/` or `hooks/`.
- **`tests/test_plugin_mirror_parity.py`** — `plan.md` and `orchestrator-review.md` under `skills/build/references/`, plus all of `skills/critical-review/`.

**Verified live drift in the parity test's own mapping.** `skills/build/` exists on disk and appears in `justfile:617`'s SKILLS array but is **absent** from `PLUGINS` — zero parity coverage today, silently, via the `continue` branch in `_discover_pairs()`. `"lifecycle"` and `"diagnose"` are in `PLUGINS` but no longer exist on disk. The mechanism meant to catch mirror drift has itself drifted, exactly as its docstring warned.

**Consequence, correcting an in-report contradiction:** because `skills/build/` is uncovered by the glob test, `test_plugin_mirror_parity.py` is currently the **only** parity coverage of `skills/build/references/plan.md` and `orchestrator-review.md`. It is *not* the redundant subset it was described as.

A completeness assertion (every `skills/*` dir appears in the mapping, hard-fail otherwise) has direct precedent in Phase 1's own fail-closed classification guard (`.githooks/pre-commit:44-58`) and would have caught the `"build"` omission the day it happened.

---

## Test & Regression Surface

### `tests/test_drift_enforcement.sh` disposition

289 lines, seven subtests (`:7-33`). Shared setup stashes pre-existing dirt on the mutated paths (`:56-62`) with `cleanup_on_exit` restoring on trap EXIT (`:64-73`); each subtest resets via `just build-plugin || true` (`:112,141,165,189,247,280`). None of that depends on Phase 4.

| Subtest | Seeds | Exercises | Under a *deleted* Phase 4 | Under the *repaired* Phase 4 |
|---|---|---|---|---|
| A (`:85-108`) | marker in `skills/commit/SKILL.md` | 2→3→4 | breaks | needs assertion update (mirror now auto-staged, hook exits 0) |
| B (`:114-137`) | marker in `hooks/cortex-validate-commit.sh` | 2→3→4 | breaks | same |
| C (`:143-161`) | marker in `cortex-ui-extras` mirror | Phase 2 non-trigger | survives | survives |
| D (`:167-185`) | marker in `cortex-pr-review` mirror | Phase 2 non-trigger | survives | survives |
| E (`:191-215`) | unclassified plugin dir | Phase 1 fail-closed | survives | survives |
| F (`:220-243`) | hand-edit to `cortex-core` mirror | 2→3→4 | breaks | needs assertion update |
| G (`:249-276`) | marker in `claude/hooks/cortex-tool-failure-tracker.sh` | Phase 2 `claude/hooks/` arm | breaks | needs assertion update |

Under the **chosen repair**, A/B/F/G do not disappear — their subject survives and their *assertions* invert from "hook exits non-zero" to "hook exits zero **and** the mirror was corrected and staged into the commit." That is a strictly better test than today's.

### C/D/E coverage is uniquely load-bearing

- `grep -rln -E "BUILD_OUTPUT_PLUGINS|HAND_MAINTAINED_PLUGINS|not classified|unclassified" tests/` → only this file plus a false positive in `test_report_sandbox_denials.py` (an unrelated sandbox-EPERM bucket name).
- `grep -rln "BUILD_NEEDED" tests/` → **only this file.**
- Subtest E is the sole test anywhere of Phase 1's fail-closed unclassified-plugin guard; C/D are the sole coverage of hand-maintained-plugin exclusion.

### Subtest G's purpose vs. its assertion

Its header (`:28-32`) states the purpose: "Regression guard for the Phase 2 trigger pattern: `claude/hooks/cortex-*.sh` paths must trigger `BUILD_NEEDED` so the mirror cannot drift silently" — guarding against the original pattern's omission of four `claude/hooks/cortex-*.sh` sources (`:250-253`). Its assertion (`:264-276`) observes only Phase 4's exit code. Traced and confirmed the rewrite works: staging the file sets `BUILD_NEEDED=1` via `.githooks/pre-commit:527-528`, Phase 3 rsyncs to `plugins/cortex-overnight/hooks/` (`justfile:642`), and asserting the mirror now contains the marker is observable, with existing cleanup restoring it.

### The two parity tests

`test_dual_source_reference_parity.py` (142 lines) also carries `test_assert_pytest_fails_on_mutation` (`:128-143`) — a sentinel that mutates mirror bytes in memory and asserts the comparison helper raises, proving the check isn't a silent no-op. **That self-test principle is worth carrying forward** to whatever replaces it; a drift check with no proof it fails on injected drift is exactly the failure this repo has already hit once.

### How the suite actually runs

`just test` (`justfile:521-554`) runs `.venv/bin/pytest tests/ -q` (`:543`) — reaching both parity tests by discovery, never by name. `validate.yml` runs a curated allowlist of nine individually-named pytest files; neither parity test nor the shell script is among them. Of nine `test_*.sh` scripts under `tests/`, four are wired into `just test-*` recipes and **none** into CI — shell-test CI wiring is absent as a repo-wide pattern, not specific to this file.

### Prior art for testing a workflow file

None. `tests/test_release_artifact_invariants.py` names the workflows in its docstring (`:10-13`) but validates their *artifacts*, never parsing the YAML. No `yamllint`/`actionlint` recipe exists.

---

## Distribution & Enforcement Boundary

### The two distribution paths

**Path A — CLI wheel**, `uv tool install "cortex-command[all] @ git+…@$LATEST_TAG"` (`docs/setup.md:74-88`, `install.sh:39-62`). Always resolves a `vX.Y.Z` **tag**.

**Path B — plugin marketplace**, `/plugin marketplace add charleshall888/cortex-command` (`README.md:22-26`, `docs/setup.md:17-28`). `.claude-plugin/marketplace.json` uses relative `"source": "./plugins/<name>"`. **No plugin sets a `version` field** in any of the seven `plugin.json` manifests or marketplace entries.

### Marketplace resolution (confirmed against official docs)

- `ref` defaults to the repository default branch when the marketplace-add form supplies none — which is the documented form here. So the checkout is **`main`**.
- Version cache key falls through to "**the git commit SHA of the plugin's source**… for relative-path sources in a git-hosted marketplace" when `version` is omitted everywhere. Per the docs: "Users get updates on every new commit to the plugin's git source." **Every commit to `main` is a distinct installable version.**
- Update timing: "after your session starts, with a random delay of up to ten minutes." Third-party marketplaces default auto-update **off**, but `README.md:35` explicitly recommends turning it on.

### The wheel does not ship the mirrors

`pyproject.toml:137` — `[tool.hatch.build.targets.wheel] packages = ["cortex_command"]`, plus one unrelated `force-include` (`:145-148`). No `MANIFEST.in`, no export-ignore. **`plugins/` is shipped exclusively by Path B.** A tag-gated check therefore protects the one channel that never carries the affected content.

### Gate timing

| Gate | Trigger | Before or after consumer reachability? |
|---|---|---|
| `.githooks/pre-commit` | local `git commit`, opt-in via `just setup-githooks`, `--no-verify`-bypassable | **Before**, on every path — the only gate with this property |
| `validate.yml` | `on: push` (any ref), `on: pull_request` | **After** — Actions is post-receive; the push to `main` has already landed |
| `auto-release.yml` `validate` | `on: push: branches:[main]` | **After**, same reason |
| `auto-release.yml` `release` | `needs: validate` (`:92`) | Before the **tag** only — no bearing on `main` or the marketplace |
| `release.yml` | `on: push: tags:` | After the tag exists; moot for Path B |

**Is there a window where a drifted `plugins/` tree on `main` is installable? Yes, unconditionally, on every push.** No workflow can run pre-receive.

### The blocking lever

A failing drift check in `auto-release.yml`'s `validate` blocks the `release` job — no tag, no `CLI_PIN` bump. It does **not** block the already-landed `main` commit, does not affect marketplace reachability, and does not queue-block later pushes (`concurrency` with `cancel-in-progress: true` coalesces runs, `:42-47`). Narrow and aimed at the wrong channel.

### Push topology (high confidence, direct evidence)

`gh api repos/charleshall888/cortex-command/branches/main/protection` → `{"message":"Branch not protected","status":"404"}`. No `CODEOWNERS`. Of 4040 commits, 12 are PR merges, the most recent **2026-07-06**; zero in the last 200. Recent history is direct pushes plus `Merge branch 'main' of …` pull-reconciliations.

**Consequence:** `validate.yml`'s `pull_request` trigger never fires in practice, and no CI check can be a required status check. The local pre-commit hook is structurally the only mechanism in this repo capable of *preventing* a drifted commit from reaching `origin/main` and therefore the marketplace.

---

## Adversarial Review

### A1 — CRITICAL, reproduced twice (agent, then orchestrator independently)

**Phase 4 is the only mechanism that gets rebuilt mirrors into a commit.** Phase 3 writes to the working tree; under `git commit --only -- <paths>` (mandated by `skills/commit/SKILL.md:11`) those paths are outside the pathspec and are discarded. Phase 4's block is what forces the author to `just build-plugin`, `git add plugins/…`, and re-commit.

Orchestrator reproduction, fresh clone, hook with `553,581d` applied:

```
=== files in the new commit ===        skills/commit/SKILL.md
=== dirt left under plugins/ ===        M plugins/cortex-core/skills/commit/SKILL.md
=== marker in COMMITTED mirror? ===    NO  - mirror NOT in commit
=== marker in WORKING-TREE mirror? === YES - Phase 3 rebuilt it on disk
```

Exit 0, no warning. Fires on **every** commit touching `skills/`, `bin/cortex-*`, `hooks/cortex-*`, `claude/hooks/cortex-*`. Cascades: CI red on essentially every source-touching push (the `#386` red-by-default failure mode); `main` — which *is* the installable version — becomes permanently drifted; the leftover dirt is itself new cross-session noise.

**Disqualifying for the delete-Phase-4 design.** Any variant keeping Phase 3 while deleting Phase 4 is broken.

### A2 — CRITICAL, reproduced: extracted script silently no-ops outside repo root

Every path in the recipe body is relative. `just` cd's to the justfile's directory; plain `bash scripts/build-plugin.sh` does not. The failure is **exit 0 having done nothing**, because `justfile:613`'s `[[ -d plugins/$p/.claude-plugin ]] || { echo skipping >&2; continue; }` fires for all three plugins. Phase 3 calls with `>/dev/null 2>&1` (`.githooks/pre-commit:546`), discarding the evidence. Mitigation is one line (`cd "$(git rev-parse --show-toplevel)"`) but was not in the proposal.

### A3 — HIGH: script extraction re-splits a shared constant

`BUILD_OUTPUT_PLUGINS` (`justfile:595`) is read via `just _list-build-output-plugins` by `.githooks/pre-commit:38` (Phase 1), `.githooks/pre-commit:539` (Phase 2), and `justfile:612`. A script that cannot call `just` must hardcode the list — so the classification guard and trigger check read one list while the builder reads another. Adding `cortex-newthing` to the justfile alone would leave it classified, trigger-matched, never built, and unflagged, with three gates green.

### A4 — HIGH: the CI gate cannot clear the repo's own bar

Per `project.md:41`, the drift gate is in **neither** list, so a "survivor entry" is the wrong operation for a retirement. More importantly, **no agent produced a single instance of drifted mirrors reaching `main` or a consumer** — the only evidence in the whole ticket is the false positive. By the constraint's own words and `CLAUDE.md:33`'s front-door bar, a new CI gate cannot enter on that evidence.

### A5 — HIGH: `validate.yml` gates nothing the release path respects

`auto-release.yml` defines its **own** `validate` job (`:51-89`) — plugin-skill validation and the call-graph guard only — and `release: needs: validate` (`:92`) points at that one, not at `validate.yml`. So a drift failure in `validate.yml` produces a red X while `auto-release.yml` tags, bumps `cli_pin.py`, and pushes unimpeded.

### A6 — HIGH: the same comparand defect exists elsewhere

`.githooks/pre-commit:229-247` runs `just sync-install-guard --check`, comparing files **on disk**, triggered by staging any of `cortex_command/install_guard.py|plugins/cortex-overnight/install_guard.py|justfile` (`:237`). A session staging `justfile` is blocked by a sibling's uncommitted `install_guard.py` edit — same bug, different phase. Phases 1.96 (`:263-300`) and the install_core/server parity block (`:369-506`) warrant the same audit (high confidence on 1.95; medium on the others).

This satisfies `CLAUDE.md`'s solution-horizon test — "the same patch would apply in multiple known places you can name" — which argues for fixing the comparand rather than deleting one instance.

### A7 — HIGH: the chosen design, and the two facts that make it work

Both **verified by execution**:

1. During a `--only` commit, `GIT_INDEX_FILE` points at git's temporary index and reads correctly through it: `git diff --cached --name-only` inside the hook printed **only the pathspec'd file** — exactly the commit's content, immune to sibling WIP.
2. **A pre-commit hook can `git add` into a partial `--only` commit.** A hook running `just build-plugin && git add -- plugins/` under `git commit --only -- skills/commit/SKILL.md` produced a commit containing **both** files.

Together: build from the staged blobs into a temp tree, compare against `git show :plugins/…`, and stage the corrected result. Sibling WIP is invisible (the temp index holds HEAD's version of anything unstaged), drift is caught preventively, and the mirror rides along automatically. Cost is roughly a `git checkout-index --prefix=$TMP/` of the source dirs plus the existing rsync loop.

Naked auto-staging *without* the staged-blob build would be strictly worse (see A8) — the two halves are not separable.

### A8 — MEDIUM-HIGH: Phase 3 launders sibling WIP, and the CI remediation path publishes it

Session A is mid-edit on `skills/build/SKILL.md`. Session B commits an unrelated change. Phase 3 rebuilds all plugins from disk, writing A's half-written file into the mirror. Today Phase 4 blocks B — annoying, but the pollution never lands. With Phase 4 deleted, nothing blocks; CI goes red; and the natural remediation (`just build-plugin && git add plugins/ && commit`) **stages A's WIP and publishes it to the marketplace tip**. Consumer harm is concrete: Claude Code loads skill prose verbatim, so a truncated instruction list produces silent misbehavior rather than an error. No evidence this has occurred; the exposure is prospective.

### A9 — MEDIUM: net test coverage

The rewritten G works (traced). But under the *deleted*-Phase-4 design, post-change `just test` would have **zero** coverage of the source↔mirror property, with the surviving coverage behind a workflow that gates nothing. Partial existing CI coverage nobody surfaced: `tests/test_reference_size_ratchet.py:128-150` (`test_mirror_dirs_deduplicate`) asserts mirror↔canonical identity via hash dedupe and is blocking at `validate.yml:70-72` — but covers only `references/` directories, not `SKILL.md`, `hooks/`, or `bin/`.

### A10 — MEDIUM: documentation is understated

`grep -n "drift\|build-plugin\|Phase 4\|pre-commit" docs/plugin-development.md` returns **14 hits across ~9 passages**, not 7. Under the delete design, `CLAUDE.md:29`'s "mirrors regenerate via the pre-commit hook" would become actively dangerous — they'd regenerate but never be committed. Note also that **Phase 4's error text (`.githooks/pre-commit:577-579`) is the primary teaching surface** for the stage-your-mirrors workflow, firing exactly when the author needs it.

### A11 — MEDIUM: blind spots any regenerate-and-diff check inherits (all verified, none regressions)

- **Orphan mirror directories are invisible**: a committed `plugins/cortex-core/skills/ghost/SKILL.md` survives a rebuild with `git status --porcelain -- plugins/` empty. Phase 4 misses this too.
- A skill on disk in no `SKILLS=` array is never mirrored and never flagged.
- `plugins/` is not built solely by `build-plugin`: `install_guard.py` comes from `just sync-install-guard` (`justfile:650-720`), `cli_pin.py` is rewritten by `auto-release.yml`, and `install_core.py`/`server.py` have their own guards (`.githooks/pre-commit:369-506`). "`plugins/` clean after build" is strictly weaker than "`plugins/` is correct."

### A12 — Attacked and found sound

Fresh-clone mechanics are fine: `just build-plugin` then `git status --porcelain -- plugins/` returns 0 lines. `rsync -a` mtime preservation does **not** cause spurious output (git falls back to content hashing on stat-cache miss). No `.gitattributes`, so no eol risk; no symlinks. Widening scope to all of `plugins/` is harmless. `if: ${{ !cancelled() }}` matches the file's convention. No pre-push hook is correct — it reintroduces the same comparand problem one stage later. No ADR is defensible, though the operative record is the `project.md:41` ledger amendment, which is mandatory rather than optional.

---

## Critical Review — why the commit-gate repair was also abandoned

A spec was written for a minimal repair: delete Phase 4's drift loop, keep Phase 3's working-tree rebuild, and replace the block with `git add -- plugins/<BO>` so mirrors ride along in the commit. Four parallel reviewers produced **12 ratified A-class (fix-invalidating) objections**, and the spec was cancelled at approval on 2026-07-28. The findings below are the durable output; re-deriving them costs another full review round.

### Through-line 1 — every bound the design claimed is asserted at a granularity the primitives lack

All measured by execution, not argued:

- **`git add -- plugins/$p/` is plugin-scoped, not build-output-scoped.** `plugins/cortex-overnight/` holds 24 tracked files; `build-plugin` writes only `skills/{overnight,morning-review}/` and `hooks/cortex-*.sh`, leaving `cli_pin.py`, `install_guard.py`, `install_core.py`, `server.py`, `.mcp.json`, `hooks/hooks.json`, `.claude-plugin/plugin.json`, and two `tests/*.py` inside the swept prefix. A probe commit touching **only** `bin/cortex-jcc` published sibling WIP into four of them.
- **Those files are owned by three fail-closed guards that cannot fire.** Phases 1.95 (`:225`), 1.96 (`:252`), and 1.97 (`:365`) all gate on `git diff --cached` evaluated *before* Phase 2's `BUILD_NEEDED` computation (`:523`) and before any staging. When the hook stages `install_guard.py` or `cli_pin.py` at the end of its own run, those guards have already decided not to fire.
- **`just build-plugin` takes no pathspec**, so "that skill's mirror" names nothing. It loops all three plugins and every hard-coded `SKILLS`/`HOOKS`/`BIN` manifest — 14 skill dirs, 59 source files, 37 `bin/cortex-*` — every invocation. Measured: of the last 500 commits, 199 set `BUILD_NEEDED=1`, and **50 of those touch no `skills/` path at all**.
- **`rsync -a --delete` reads the working tree, not the index.** A sibling's uncommitted `rm` of a canonical file yields a commit that deletes the mirror while the canonical survives in HEAD — the exact source/mirror inconsistency Phase 4 existed to catch, now produced by its replacement. The recipe's unconditional `rm -f plugins/$p/hooks/cortex-*.sh` before re-rsyncing `HOOKS` is a second instance of the same class.
- **`git add` on a prefix stages untracked paths anywhere beneath it.** A sibling scratch file at `plugins/cortex-core/SIBLING-UNTRACKED-SCRATCH.md`, outside every mirrored directory, committed as `A`.
- **There is no observation channel.** `git commit --only` prints a file count with no paths on the modify path; Phase 3 is `>/dev/null 2>&1` and the staging step emits nothing. A hook-rewritten commit is observationally identical to one the hook never touched — in a hook with 9 existing `echo "pre-commit` sites, the staging step would be the only commit-mutating action that says nothing.

`BUILD_NEEDED` fires on 22.5% of all 4044 commits, 39.8% of the last 500, and 40.0% of the last 100 — so "only on commits that already touch a build-trigger path" describes a plurality, not a narrowing.

### Through-line 2 — the spec reproduced the very defect it was fixing, in its own verification layer

A comparand that does not measure what it claims. Four of eleven requirements had acceptance criteria that passed for the requirement's negation or could not be evaluated:

- The doc criterion (`grep -c 'Drift loop\|drift failure'` = 0) matched only two lines, both *inside* the passages it already mandated rewriting — returning 0 for any edit while leaving `:34`, `:41`, `:108`, and `:134` asserting a verification that no longer happens.
- The ledger criterion's two anchored greps returned 1 for an entry filed in the **retired** half of the bullet — the classification the requirement forbade.
- The test criterion asserted "the regenerated mirror is present in the resulting commit" against a harness where `grep -c 'git commit' tests/test_drift_enforcement.sh` = **0**; every subtest runs the hook standalone.
- Subtest F's rewritten assertion is arithmetically impossible: it stages only a mirror hand-edit, Phase 3 regenerates it from the untouched canonical source, the staging step re-stages a HEAD-identical blob, and the commit contains **zero files**.

### Through-line 3 — it removed every observer, then conditioned its own repair on an observation

The spec deferred any CI check until "drift reaches `main`" — while deleting every mechanism able to see that happen. `tests/test_dual_source_reference_parity.py` compares **working-tree** bytes, which are equal in precisely the case that produces the inconsistent commit (measured: working-tree parity PASS while `HEAD:skills/refine/SKILL.md` ≠ `HEAD:plugins/.../refine/SKILL.md`), and no workflow runs it. The escape hatch was unreachable by construction.

### Corrections to earlier sections of this document

- **`just test` does wire shell tests.** `justfile:542` is `run_test "test-install" bash tests/test_install.sh`, one line above the `:543` cited above. `tests/test_drift_enforcement.sh`'s unreachability is a one-line wiring omission, not a property of the runner.
- **`skills/commit/SKILL.md:14`** states "Concurrent sessions share one git index, so a bare `git commit` sweeps whatever a sibling session staged — the trailing pathspec with `--only` is what makes this safe." Any hook-side `git add` re-introduces that sweep *after* the pathspec is applied, and from a sibling's **unstaged** working tree, which even a bare `git commit` would not take. Any future design that stages from within the hook invalidates this claim and must amend it.
- **`docs/plugin-development.md` has zero inbound references** (`grep -rl` across `README.md docs/ skills/ plugins/ hooks/ claude/ justfile CLAUDE.md` → no matches). It is not a viable relocation target for instructions currently carried by a runtime error message.

### Where this leaves the problem

Three designs have now been disproved: relocating enforcement to CI (kills mirror maintenance, wrong channel, unreachable by any pre-receive gate), deleting Phase 4 outright (same), and replacing the block with working-tree staging (the 12 objections above). The staged-blob build remains untried and closes through-line 1 at the root, but was not attempted.

The reconsideration the operator chose instead: **#411's root cause is two Claude Code sessions sharing one physical working tree.** Every false positive, every laundering path, and every clobber risk in this document derives from that, not from the comparand. Isolating concurrent sessions — worktrees, or a session-scoped index — would make the comparand question moot without touching the hook. That is the direction to evaluate before any further work on `.githooks/pre-commit`.

## Open Questions

1. **Do the sibling comparand defects (A6) get fixed here or filed separately?** — **Resolved: audit in scope, fix scoped to Phase 1.95.** Phase 1.95 is confirmed same-shape and is triggered by staging `justfile`, which this change does, so leaving it would let this change's own commit hit the bug it fixes. Phases 1.96 and the install_core/server parity block are medium-confidence and unverified; the spec should require an audit and file a follow-up ticket rather than speculatively rewriting them.

2. **Does `tests/test_dual_source_reference_parity.py` get repaired or deleted?** — **Resolved: repaired, not deleted.** Its `PLUGINS` dict is verifiably broken (`skills/build/` uncovered; dead `lifecycle`/`diagnose` entries), and deleting it while it is the only thing standing between `just test` and zero source↔mirror coverage would trade a fixable bug for a coverage hole. Repair requires: add `"build"`, drop the dead entries, and add the Phase-1-style completeness assertion so an unlisted skill dir fails loudly. `tests/test_plugin_mirror_parity.py` remains genuinely redundant **only once** `"build"` is restored to the glob test's mapping — sequence the deletion after the repair, in that order, or the `skills/build/references/` coverage gap opens.

3. **Does the ticket body get rewritten as part of this change?** — **Resolved: yes.** #418's title, Why, Role, Integration, Edges, and Touch points all describe a disproved design. The lifecycle slug stays as-is (identity key). Retitling via `cortex-update-item` must not disturb `lifecycle_slug` resolution — verify before applying.

4. **Should Phase 3 build from staged blobs for *all* build-output plugins, or only those whose sources this commit touches?** — **Deferred to Spec with rationale.** Both are correct with respect to the false positives once the comparand is staged-blobs; the choice is a performance/simplicity trade (`build-plugin` runs in ~0.5s, so the full rebuild is likely fine and avoids needing the skill→plugin map that `justfile:615-635` currently owns exclusively). Needs the implementation shape settled before it can be decided, which is Spec's job, not Research's.

5. **Is there any evidence drift has ever actually reached `main`?** — **Resolved: no, and none was found.** Six angles searched; the only evidenced failure is the false positive. This is why no CI gate ships (A4) and why the `project.md:41` ledger entry records a *repair*, not a new gate. Should drift ever reach `main`, that incident becomes the named evidence admitting a CI check.

6. **Symlink-based root removal of the dual-source burden.** — **Deferred with rationale.** The skill→plugin mapping is a clean partition, so the idea is sound in principle, but it hinges on an unverified external constraint (whether Claude Code's plugin loader follows a symlink escaping the plugin root) and inverts assumptions held by `CLAUDE.md`, ADR-0009, `cortex-check-skill-path`, and the contract linter. Warrants its own spike ticket with a verification-first task; explicitly out of scope here.
