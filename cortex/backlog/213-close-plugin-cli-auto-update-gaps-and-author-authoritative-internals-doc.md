---
schema_version: "1"
uuid: 4f90fc64-cae9-4a87-9245-8256ddf9b234
title: "Close plugin/CLI auto-update gaps and author authoritative internals doc"
status: complete
priority: high
type: feature
created: 2026-05-13
updated: 2026-05-14
discovery_source: 210-refresh-install-update-docs-close-mcp-only-auto-update-gaps.md
tags: [mcp, upgrade, internals, plugin]
session_id: null
lifecycle_phase: research
lifecycle_slug: close-plugin-cli-auto-update-gaps
complexity: complex
criticality: high
spec: cortex/lifecycle/close-plugin-cli-auto-update-gaps/spec.md
areas: [overnight-runner,skills]
---

## Intent (what the system is supposed to deliver)

The cortex-overnight plugin and cortex CLI are designed to stay version-coupled through a two-layer auto-update flow:

1. **Layer 1 — marketplace auto-update at Claude Code startup** (verified working). Claude Code's plugin marketplace fast-forwards the cortex-command plugin clone on each session start. The plugin's `CLI_PIN` literal at `plugins/cortex-overnight/server.py:105` is the plugin's declaration of "I require CLI git-tag X."
2. **Layer 2 — MCP-tool-call-gated pre-delegate auto-update** (currently NOT delivered under wheel install). On every MCP tool call, the plugin's MCP server should detect when the installed CLI version doesn't match `CLI_PIN[0]` and reinstall via `uv tool install --reinstall git+url@CLI_PIN[0]` under a flock. PATH wiring is the responsibility of `uv tool install` (with `uv tool update-shell` as the documented remediation when a stale shell misses the PATH update).

The user-visible promise is: maintainer cuts a release with a bumped `CLI_PIN` → marketplace fast-forwards the user's plugin clone within one Claude Code session start → the next MCP tool call transparently reinstalls the user's CLI to the new tag. The user never runs `uv tool upgrade` manually.

This is a single-ticket plan to deliver that intent end-to-end AND to author the authoritative internals doc so future sessions stop confusing "intent" with "currently wired."

## Why this ticket exists

#210 (`refresh-install-update-docs-close-mcp`) was meant to "refresh install/update docs + close MCP-only auto-update gaps." The refine phase grounded its claims on the prior investigation at `cortex/lifecycle/investigate-plugin-auto-update-not-fetching-from-origin/findings.md`, which classified the system as "expected behavior" — but that investigation explicitly scoped Layer 2 (the inner CLI_PIN comparison + reinstall) as research-context only, never validated. #210's docs (R5/R6/R7 in `docs/setup.md ## Upgrade & maintenance`, the README "Recommended:" bullet, the §1a preflight prose) codified the intended flow as canonical present-tense. The system being documented does not run as described under wheel install.

Surfaced by the maintainer dogfooding the plugin install path (not the local-dev `uv tool install --from .` path) post-#210 and immediately hitting `cortex-daytime-pipeline not on PATH` plus a stale install. Four parallel adversarial agents (opus) traced the call graph end-to-end and cross-corroborated the three gaps below.

## Gap A — `CLI_PIN` doesn't propagate from git tag to plugin source

`docs/release-process.md` step 7 prescribes a manual edit of the `CLI_PIN` literal at `plugins/cortex-overnight/server.py:105` after the CLI tag is pushed. Empirical record across `v0.1.0 → v1.0.0 → v1.0.1 → v1.0.2`:

```
$ for t in v0.1.0 v1.0.0 v1.0.1 v1.0.2; do
    echo -n "$t: "
    git show $t:plugins/cortex-overnight/server.py | grep -E '^CLI_PIN\s*=\s*\('
  done
v0.1.0: CLI_PIN = ("v0.1.0", "1.0")
v1.0.0: CLI_PIN = ("v0.1.0", "1.0")
v1.0.1: CLI_PIN = ("v0.1.0", "1.0")
v1.0.2: CLI_PIN = ("v0.1.0", "1.0")
```

3-for-3 violation of the documented release ritual. The manual step is reliably skipped because it's inconspicuous (no CI feedback, no user-visible signal until users hit version-skew much later). #212 (`CLI_PIN drift lint`) was filed as a symptom-fix; this ticket subsumes it with a root-cause fix that eliminates the manual step entirely.

## Gap B — `pyproject.toml` `version` stays frozen at `"0.1.0"` across all 4 tags

```
$ for t in v0.1.0 v1.0.0 v1.0.1 v1.0.2; do
    echo -n "$t: "
    git show $t:pyproject.toml | grep '^version'
  done
v0.1.0: version = "0.1.0"
v1.0.0: version = "0.1.0"
v1.0.1: version = "0.1.0"
v1.0.2: version = "0.1.0"
```

Wheels built from `v1.0.2` are named `cortex_command-0.1.0-py3-none-any.whl`. `cortex --print-root --format json` reports `"version": "1.1"` regardless of which tag was installed (because `cortex_command/cli.py:226` hardcodes the envelope-version string independently). `importlib.metadata.version("cortex-command")` returns `0.1.0` on a `@v1.0.2` install. This breaks any consumer doing version-based routing AND makes the `CLI_PIN[0]` comparison meaningless because no observable surface reflects the supposedly-installed tag.

`docs/release-process.md:21-23` explicitly mandates `pyproject.toml version == tag-without-v`. The mandate is violated 3-for-3 by the same root cause as Gap A: the documented release process asks the human to update three things in lockstep, and only the conspicuous one (the git tag) reliably happens.

## Gap C — R4 (`_ensure_cortex_installed`) does not do version comparison under wheel install

The function at `plugins/cortex-overnight/server.py:443-470` gates as `if shutil.which("cortex") is not None: return`. Zero version check. Under wheel install + cortex-already-installed (the dominant runtime case), R4 ALWAYS early-returns regardless of `CLI_PIN[0]`.

The deprecation comments at `server.py:1354/1363/1554/1562` ("R10 orchestration deprecated under wheel install (Task 16)") retire the OLD git-working-tree upgrade path (where `cortex upgrade` did a `git pull` under `$cortex_root/.git/cortex-update.lock`) and claim "R4 first-install hook + R13 schema-floor gate is the upgrade arrow." But:

- R4's first-install hook only fires when `cortex` is missing from PATH.
- R13's schema-floor gate (`server.py:1499-1565`) short-circuits when `cortex_root` has no `.git` dir — which is the case for every wheel install. The comment at 1554-1565 explicitly notes "Task 9's R4 first-install hook handles the schema-floor major-mismatch reinstall under wheel install" — but R4 doesn't do that. The "handles" claim is aspirational, not wired.
- R8 upstream-advance check (`_maybe_check_upstream` at `server.py:924`) also requires a `.git` dir at `cortex_root`.

So under wheel install — the install path users follow per `docs/setup.md` — none of R4, R8, or R13 actually fires a version-mismatch reinstall. The orchestration's intent is unrealized in the dominant code path.

## Empirical confirmation

- `~/.local/state/cortex-command/` does not exist on a machine actively using cortex-overnight (no `install.lock`, no `install-failed.*` sentinels, no `last-error.log`). The R4 install branch — the only writer of that directory via `_acquire_install_flock` at `server.py:411` — has never executed in 4 release cycles.
- All orchestration tests (`tests/test_no_clone_install.py:355-500`, `tests/test_mcp_auto_update_orchestration.py:1310`) are 100% mocked control-flow. None exercise a real `uv tool install` or a real version mismatch. The R13 test injects a `"version": "0.9"` major that's structurally unreachable in production (the CLI hardcodes `"1.1"`; `MCP_REQUIRED_CLI_VERSION` is `"1.0"`; both major=1).
- #210's docs (R5/R6/R7 in `docs/setup.md ## Upgrade & maintenance`, the README "Recommended:" bullet at line 33, the §1a preflight prose at `skills/lifecycle/references/implement.md:90-101`) describe the intended Layer 2 flow as canonical present-tense. The §1a preflight even hardcodes `@v0.1.0` in its remediation hint (commit 574433fe, landed during #210 implement) — propagating the stale literal into the prose meant to detect staleness.

## Fix direction (single ticket; ordered by leverage)

### 1. Adopt hatch-vcs for dynamic versioning

Change `pyproject.toml`:
- Remove `version = "0.1.0"` from `[project]`.
- Add `dynamic = ["version"]` to `[project]`.
- Add `[tool.hatch.version]` section with `source = "vcs"`.
- Add `hatch-vcs` to `[build-system] requires` (it's a PyPA-org package, no new external trust).

Closes Gap B. Wheels become correctly named (e.g. `cortex_command-1.0.3-py3-none-any.whl` at tag `v1.0.3`). `cortex --print-root` should also derive its emitted version from `importlib.metadata.version("cortex-command")` rather than the hardcoded `"1.1"` at `cortex_command/cli.py:226` — bundle that one-line change into this work since the envelope-version-drift is a related symptom.

### 2. Auto-derive `CLI_PIN` at plugin package time

Replace the literal tuple at `server.py:105` with `from cortex_overnight._version import CLI_PIN`, where `_version.py` is generated at plugin-build time from `git describe --tags --abbrev=0` (resolving the latest tag on the cortex-command repo). The plugin's build step writes the resolved tuple; humans never edit the literal.

Closes Gap A. The most failure-prone manual step in the release ritual disappears.

### 3. Wire version-comparison into R4

In `_ensure_cortex_installed` at `server.py:443`, after the existing `shutil.which("cortex") is not None` early-return passes, add a second check: run `cortex --print-root --format json` (or `cortex --version` once that's wired to derive from `importlib.metadata`), parse the installed version, and compare against `CLI_PIN[0]`. If they differ, fall through to the same reinstall branch the function already has (lines 524-555). Preserve the recent-sentinel short-circuit, the flock acquisition, the post-install verification, and the NDJSON audit record.

Closes Gap C. Actually delivers the upgrade behavior the deprecation comments at 1554-1565 claim is wired.

### 4. Add a real-install integration test

Add `tests/test_mcp_auto_update_real_install.py`. In a `tmp_path`-isolated env with a clean `uv tool` directory:

1. Build a wheel from a synthetic `v0.1.0` source tree and `uv tool install` it.
2. Confirm `cortex --print-root` reports `0.1.0`.
3. Build a wheel from a `v0.2.0` source tree and write a copy of the plugin source with `CLI_PIN = ("v0.2.0", "1.0")`.
4. Invoke the orchestration entry point (`_ensure_cortex_installed` or `_resolve_cortex_argv`).
5. Assert: the CLI is reinstalled, `cortex --print-root` now reports `0.2.0`, a `last-error.log` exists (or doesn't, depending on success path), the install lockfile was acquired and released, the success NDJSON audit record is present.

The current mocked tests would not have caught Gap C; this one would. Skip if `uv tool` is unavailable on the runner.

### 5. Author `docs/internals/auto-update.md` as the authoritative internals doc

Per CLAUDE.md's "Overnight docs source of truth" convention (`docs/overnight-operations.md` owns the round loop; `docs/internals/pipeline.md` owns pipeline-module internals; `docs/internals/sdk.md` owns SDK model-selection mechanics), this new doc owns the auto-update flow. Required sections:

- **Intent** — what the user-visible promise is, in plain English.
- **Two-layer architecture** — Layer 1 (marketplace), Layer 2 (MCP-tool-call-gated). The wheel-install vs editable-install distinction. The "Bash-tool subprocess dispatches don't trigger Layer 2" carve-out (the #145 wontfix).
- **Component map** — every load-bearing component, file:line, and what fires it. Specifically: `CLI_PIN` (auto-derived from latest tag, post-fix); `_resolve_cortex_argv` hot path; `_ensure_cortex_installed` (R4) with the version-comparison branch this ticket adds; `_maybe_check_upstream` (R8, git-tree-only — explicitly documented as legacy editable-install path); R13 schema-floor gate.
- **Release ritual (minimum viable)** — post-fix, this collapses to: edit `CHANGELOG.md`, `git tag -a vX.Y.Z`, `git push --tags`. Three steps, zero source-file edits.
- **"Intent vs. currently wired" audit table** — for each component, declare whether the doc describes intended behavior (with a pointer to the ticket that wires it) or currently-running behavior. Future sessions reading this doc can audit it against the code without ambiguity.

Link from `docs/setup.md ## Upgrade & maintenance` (which becomes a user-facing pointer, not a duplicated description), from `README.md`, and from the CLAUDE.md "internals docs source of truth" list.

### 6. Rewrite #210's R5/R6/R7 docs to match post-fix state

Once (1)-(3) land:

- `docs/setup.md ## Upgrade & maintenance` becomes a shorter user-facing summary that points to `docs/internals/auto-update.md` for the mechanism. The "two-layer" framing stays, but the present-tense claims become accurate.
- `README.md`'s "Recommended:" bullet (line 33) gets the same shortening — keeps the mechanism summary, points to the internals doc.
- `skills/lifecycle/references/implement.md`'s §1a preflight remediation hint should pull the install command from a single source-of-truth (or, since this is a skill prose file, hardcode the canonical install URL but parameterize the tag as `@<latest>` with a build-time substitution OR explicit instruction to read `CLI_PIN[0]`). Eliminate the hardcoded `@v0.1.0` propagating-rot literal.

Update the parity test at `tests/test_lifecycle_kept_pauses_parity.py` only if any line-anchor SKILL.md inventory entries are affected.

### 7. Close superseded follow-ups

- **#211** (`R8 cwd-vs-installed-wheel divergence`): becomes much simpler under hatch-vcs because `importlib.metadata.version("cortex-command")` becomes the source-of-truth for "what tag am I installed at," eliminating the cwd-vs-installed-wheel discrepancy R8 was working around. Mark as superseded by this ticket on land; the residual work folds into Fix Direction (1).
- **#212** (`CLI_PIN drift lint`): becomes moot under auto-derivation in Fix Direction (2). A lint detects stale state; auto-derivation eliminates the stale state structurally. Mark as superseded by this ticket on land.

## Acceptance

A. `pyproject.toml` has `dynamic = ["version"]` and a `[tool.hatch.version]` section. `uv build --wheel` from a clean checkout produces a wheel whose filename matches `git describe --tags`. `cortex --print-root --format json` on the installed wheel reports the same tag. `importlib.metadata.version("cortex-command")` returns the same value. `grep -E '^version\s*=\s*"' pyproject.toml` returns zero matches.

B. `CLI_PIN` at `plugins/cortex-overnight/server.py` is imported from a build-generated `_version.py`. `grep -nE 'CLI_PIN\s*=\s*\(' plugins/cortex-overnight/server.py` returns zero matches outside of comments. `grep -rE 'CLI_PIN\s*=\s*\(' plugins/ tests/ cortex_command/` returns matches only in test fixtures and the archive.

C. `_ensure_cortex_installed` at `server.py` includes a version-mismatch branch that fires when `cortex` is on PATH but reports a version != `CLI_PIN[0]`. The reinstall branch is reachable on real wheel installs.

D. New `tests/test_mcp_auto_update_real_install.py` exists, exercises a real `uv tool install` in a tmpdir-isolated env, and asserts version-mismatch triggers reinstall. `just test` exits 0.

E. End-to-end live test on the maintainer's machine: cut a `vX.Y.Z`-tagged release with bumped pyproject (auto-derived via hatch-vcs) and auto-derived CLI_PIN; observe via `git -C ~/.claude/plugins/marketplaces/cortex-command/ reflog --date=iso` that marketplace fast-forwards the plugin clone within one Claude Code session start; invoke an MCP tool; observe via fresh sentinel + `install.lock` at `~/.local/state/cortex-command/` that R4 triggered the reinstall and the installed CLI now reports the new tag.

F. `docs/internals/auto-update.md` exists, names every load-bearing component (file:line), and is linked from `docs/setup.md ## Upgrade & maintenance`, `README.md`'s "Recommended:" bullet, and CLAUDE.md's overnight-docs source-of-truth list. The doc includes an explicit "intent vs. currently wired" audit table. `grep -q 'docs/internals/auto-update' docs/setup.md README.md CLAUDE.md` succeeds.

G. `#211` and `#212` are marked `status: complete` (or `status: superseded`) with body notes pointing to this ticket's slug as the canonical origin. `cortex/backlog/index.md` reflects the new statuses after `just backlog-index`.

H. The §1a preflight remediation hint at `skills/lifecycle/references/implement.md` no longer hardcodes `@v0.1.0`. Either the literal is replaced by a parameterized reference to `CLI_PIN[0]`, or the prose instructs the user to `uv tool upgrade cortex-command` (deferring tag resolution to `uv tool`).

## Origin

Surfaced during /cortex-core:lifecycle resume of `refresh-install-update-docs-close-mcp` (#210). The lifecycle landed 11 tasks across 4 batches and was APPROVED at review cycle 1 — but the refine phase did not validate that the documented two-layer flow actually runs under wheel install. Adversarial multi-agent investigation post-implement (4 parallel agents, opus model) traced the call graph end-to-end and confirmed the three gaps above with cross-corroborated evidence. Specifically:

- Agent A traced `_ensure_cortex_installed` and quoted the originating spec from `cortex/lifecycle/archive/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/spec.md:7`.
- Agent B found zero on-disk fires and surfaced the deprecation comments at `server.py:1354/1363/1554/1562`.
- Agent C corrected an initial conflation between `_ensure_cortex_installed` (missing-CLI only) and the version-coupling path (R8/R13).
- Agent D's comparative analysis cited hatch-vcs / setuptools-scm, GitHub Actions pinning, Terraform required_version, and VS Code extension bundling as analogous patterns — none of which embed a literal CLI tag string in plugin source that requires hand-bumping.

The §1a preflight prose at `skills/lifecycle/references/implement.md` now hardcodes `@v0.1.0` (commit 574433fe, landed during #210 implement) because the plan's verification token required the literal `--reinstall` substring and the most natural prose form picked up the stale tag — this is the propagating-rot symptom the auto-derive fix eliminates structurally.

This ticket consolidates #146 finish, #211, and #212 into a single delivery so the auto-update orchestration runs end-to-end AND the docs match the running system before the next release.
