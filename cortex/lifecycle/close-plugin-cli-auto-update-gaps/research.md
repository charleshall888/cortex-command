# Research: Close plugin/CLI auto-update gaps and author authoritative internals doc

## Epic Reference

This ticket descends from [[210-refresh-install-update-docs-close-mcp-only-auto-update-gaps]] (`cortex/lifecycle/refresh-install-update-docs-close-mcp/`). #210 landed docs claiming the two-layer auto-update flow works under wheel install, but did not validate that the documented Layer 2 (MCP-tool-call-gated reinstall) actually runs end-to-end — the gaps surfaced here (A: CLI_PIN drift; B: frozen package version; C: R4 missing version-comparison) were discovered post-implement by maintainer dogfooding. This research is scoped strictly to #213's mechanism-delivery and authoritative-doc work; #210's docs (`docs/setup.md ## Upgrade & maintenance`, README "Recommended:" bullet, §1a preflight) are referenced as code-to-rewrite, not as background concerns.

## Codebase Analysis

### Files that will change — grouped by the seven Fix Directions

**FD1 — Adopt hatch-vcs for dynamic versioning (Gap B)**
- `pyproject.toml:1-7,43-53`: drop `version = "0.1.0"`, add `dynamic = ["version"]`, add `[tool.hatch.version] source = "vcs"`, add `hatch-vcs` to `[build-system] requires`. Existing config (`requires = ["hatchling>=1.27"]`, backend `hatchling.build`) makes `hatch-vcs` a one-line additive change. Configure `[tool.hatch.build.hooks.vcs] version-file = "cortex_command/_version.py"`.
- `cortex_command/cli.py:225-231` (envelope `"version": "1.1"` in `_dispatch_print_root`): **DO NOT conflate** the envelope-version field with the package version. The docstring at :166-170 makes the envelope-vs-package distinction explicit. Spec must split this into two operations — see Adversarial §3.N and Open Question (a).
- `.gitignore`: add `cortex_command/_version.py` (hatch-vcs generated; should NOT be committed — per hatch-vcs footgun documented at https://github.com/maresb/hatch-vcs-footgun-example).
- `.github/workflows/release.yml`: add `fetch-depth: 0` and `fetch-tags: true` to `actions/checkout@v4`. Default shallow checkout breaks hatch-vcs — see Adversarial §2.K.

**FD2 — Auto-derive `CLI_PIN` at plugin package time (Gap A)**

⚠️ **The ticket's framing of FD2 is architecturally non-viable under the plugin's marketplace-git-clone distribution.** The plugin is a PEP 723 single-file script (`uv run --script` per the header at `plugins/cortex-overnight/server.py:1-8`) distributed by Claude Code marketplace as a git clone (per `.claude-plugin/marketplace.json:24-29`, source = `./plugins/cortex-overnight`). There is no plugin wheel and no plugin build step. The ticket's prescription "_version.py is generated at plugin-build time" has no plugin-build time to hook into. See Adversarial §1.A and §1.L.

Tradeoffs research (Agent 4) and adversarial review converge on a **structural redesign of FD2**:

- **Recommended**: Replace FD2 with a **CI lint in release.yml** that compares the `CLI_PIN[0]` literal at `plugins/cortex-overnight/server.py:105` against the pushed tag string and fails the release on mismatch. This gives the conspicuous CI failure signal the manual ritual currently lacks, without inventing a non-existent plugin build step. The maintainer still edits `CLI_PIN` manually before tagging — but CI hard-fails the release if they forget.
- **Alternative also worth considering**: a `.cli-pin` text file in `plugins/cortex-overnight/` plus the same CI lint. Lower-noise diffs (single-purpose file), but functionally the same human-reliability profile as the in-source literal — the value is in the CI lint, not the file format. The literal is fine; the value is the lint.
- **NOT viable**: build-time `_version.py` generation (the ticket's text) because there's no plugin build to hook into; bootstrap paradox if the maintainer runs `git describe` before tagging.
- **NOT viable**: `git-archive export-subst` — marketplace fast-forward uses `git fetch + git reset`, not `git-archive`. Smudge filters don't fire.

Files affected by the recommended approach:
- `.github/workflows/release.yml` (new): add a step on tag push that runs a CLI_PIN consistency check against `git describe --tags HEAD`. Fails the workflow on mismatch.
- `tests/test_release_artifact_invariants.py` (new): asserts `git describe --tags` of HEAD equals `CLI_PIN[0]` reference in plugin source on any tag-named commit. Catches the inversion at CI time even before release.yml fires.
- `docs/release-process.md:98-120` (the "Conditional Bump the plugin's CLI_PIN" section): rewrite to describe the CI-enforced check instead of deleting the section. The manual `CLI_PIN` edit step stays, but is now CI-gated.

**FD3 — Wire version-comparison into R4 (Gap C)**
- `plugins/cortex-overnight/server.py:443-470` (`_ensure_cortex_installed`): after the existing `shutil.which("cortex") is not None` early-return, add a version-compare branch. **Critical detail surfaced by adversarial research**: the new branch must read the package version from a **new envelope field** (`payload["package_version"]`), not the existing envelope-version field (`payload["version"]`), to avoid breaking the 5 schema-version consumers — see Open Question (a).
- `plugins/cortex-overnight/server.py:124-138` (`_parse_major_minor` / `_check_version`): the existing parser splits on `"."` with `maxsplit=1` and `int()`-coerces both halves. A PEP 440 string like `"1.0.3"` becomes `("1", "0.3")` → `int("0.3")` raises `ValueError`. A hatch-vcs dirty-checkout local-version suffix like `"1.0.3.dev1+gabc1234"` makes it worse. Replace with `packaging.version.Version`-based comparison. Add `packaging` to the plugin's PEP 723 dependency declaration in the script header (currently only `mcp` and `pydantic`).
- `plugins/cortex-overnight/server.py:798-852` (`_append_error_ndjson`) and `:373-396` (sentinel writer): reuse existing patterns for the new branch's audit record. Register a new stage value (e.g., `"version_mismatch_reinstall"`) at `server.py:772-780`'s `_NDJSON_ERROR_STAGES`.
- **In-flight guard inheritance gap** (Adversarial §1.B): `cortex_command/install_guard.py` is NOT importable from the plugin's PEP 723 venv. R4's reinstall branch currently does not consult `check_in_flight_install` at all. The new version-compare branch must inline a session-detection check (read `~/.local/share/overnight-sessions/active-session.json` directly, verify runner pid without psutil) and respect the `CORTEX_ALLOW_INSTALL_DURING_RUN=1` bypass plus the `CORTEX_RUNNER_CHILD=1` carve-out. Without this, R4 silently rewrites the running CLI mid-overnight-run.
- `plugins/cortex-overnight/server.py:1354-1366,1554-1566` (deprecation comments): rewrite to match the new wiring — they currently claim R4 "handles" schema-floor major-mismatch reinstall under wheel install, which becomes true only post-FD3.
- `plugins/cortex-overnight/server.py:1499-1565` (R13 schema-floor gate): when the gate fires under wheel install (no `.git` dir), the current short-circuit returns silently. Replace with a stderr surface ("schema-floor violation detected but no upgrade path — please run `uv tool install --reinstall git+...@CLI_PIN[0]` manually") so the silent-degraded mode becomes observable.
- `tests/test_no_clone_install.py:355-500` (`test_mcp_first_install_hook`): the existing test patches `shutil.which("cortex")` to return `None`, so the new version-compare branch is NEVER traversed by existing tests. False-positive coverage. Add a new phase that mocks `shutil.which` returning a fake path AND mocks `cortex --print-root --format json` returning a stale tag, then asserts reinstall fires.

**FD4 — Add a real-install integration test**
- `tests/test_mcp_auto_update_real_install.py` (new): mirror fixture pattern from `tests/test_no_clone_install.py:113-144` (`_install_wheel_isolated`) and `tests/test_mcp_auto_update_orchestration.py:1116-1158`. Both use `UV_TOOL_DIR` + `UV_TOOL_BIN_DIR` redirected into `tmp_path` (which lives under `$TMPDIR`, already in the global sandbox allowWrite — no allowWrite expansion needed). Mark `@pytest.mark.slow` + `@pytest.mark.serial`.
- Test phases: (1) build wheel A at synthetic v0.1.0, install via `uv tool install`, assert `cortex --print-root` reports `package_version=0.1.0`; (2) build wheel B at v0.2.0 + write tmp plugin source with `CLI_PIN = ("v0.2.0", "1.0")` (substitutes for marketplace fast-forward); (3) invoke `_ensure_cortex_installed()` against freshly-loaded server module; (4) assert reinstall fired, post-install `cortex --print-root` reports v0.2.0, `install.lock` was acquired and released at the isolated `XDG_STATE_HOME/cortex-command/`, success NDJSON record landed. Use `HATCH_BUILD_HOOK_VCS_FALLBACK_VERSION` to pin synthetic versions for the fixture wheels.
- Add three new test paths (per Adversarial §4 mitigation 4): (a) `shutil.which` returns fake path + version mismatch → reinstall fires; (b) `shutil.which` returns fake path + active-session pointer present → abort with guard error; (c) R13 schema-floor on wheel install (no `.git` mkdir) → R4's reinstall branch fires. The third paths back-stops the existing test gap at `tests/test_mcp_auto_update_orchestration.py:1335` which `.git/.mkdir`s and thus never exercises the wheel-install dormancy path.

**FD5 — Author `docs/internals/auto-update.md`**
- `docs/internals/auto-update.md` (new): joins the existing internals-doc inventory at `docs/internals/{events-registry.md, mcp-contract.md, one-shot-scripts.md, pipeline.md, sdk.md}`. Required sections per ticket lines 127-132: Intent, Two-layer architecture, Component map (file:line anchors), Release ritual (minimum viable), "Intent vs currently-wired" audit table.
- Component anchors to capture (verified during research):
  - `plugins/cortex-overnight/server.py:105` (CLI_PIN)
  - `plugins/cortex-overnight/server.py:443` (`_ensure_cortex_installed`, R4)
  - `plugins/cortex-overnight/server.py:650` (`_resolve_cortex_argv`)
  - `plugins/cortex-overnight/server.py:924` (`_maybe_check_upstream`, R8; explicitly mark as legacy editable-install path)
  - `plugins/cortex-overnight/server.py:1499` (`_schema_floor_violated`, R13)
  - `cortex_command/cli.py:225` (envelope-version field; post-FD1 spec also adds `package_version` field)
- `CLAUDE.md:50` (overnight-docs source-of-truth list): add a line for `docs/internals/auto-update.md`.

**FD6 — Rewrite #210's R5/R6/R7 docs to match post-fix state**
- `docs/setup.md:188-227` (## Upgrade & maintenance, especially "two-layer upgrade model" at :198-207 + CORTEX_ALLOW_INSTALL_DURING_RUN callout at :209-219): shorten to user-facing summary; insert pointer to `docs/internals/auto-update.md`. The MCP-tool-call-gated language stays correct; the "R4 reinstalls on mismatch" claim at :194-196 becomes factually accurate only post-FD3.
- `README.md:33` (the "Recommended:" bullet): shorten, point to internals doc.
- `skills/lifecycle/references/implement.md:90-101` (§1a preflight remediation hint): currently hardcodes `@v0.1.0` at :100. Replace with `uv tool upgrade cortex-command` (defers tag resolution to `uv tool`) OR a parameterized reference to `CLI_PIN[0]`. Verified: §1a is NOT in the kept-pauses parity inventory at `skills/lifecycle/SKILL.md:189-201` (which tracks `implement.md:22` for branch-selection AskUserQuestion). The parity test has LINE_TOLERANCE=35 (`tests/test_lifecycle_kept_pauses_parity.py:27`); §1a's prose-only edit doesn't risk anchor drift to the tracked line.
- **Stale-tag literals missed by the ticket's FD6 enumeration** (Adversarial §1.Q):
  - `install.sh:41`: `tag="${CORTEX_INSTALL_TAG:-v0.1.0}"` — env-var override is good, but the default literal still misleads readers.
  - `docs/setup.md:27`: install command Quickstart fence still has `@v0.1.0`.
  - Spec must enumerate every stale `@v0.1.0` literal and decide replacement strategy. The grep-anchor: `git grep '@v[0-9]'` against the working tree.

**FD7 — Close superseded follow-ups**
- `cortex/backlog/211-r8-should-track-installed-wheel-commit-not-cwd-working-tree-head-146-follow-up.md`: change `status: backlog` → `status: superseded` (or `complete`); add body note pointing to #213. Run `cortex-update-item 211-... status=superseded`.
- `cortex/backlog/212-cli-pin-drift-lint-146-hygiene.md`: same treatment. **Note**: the CI-lint recommended in FD2 is morally the same idea as #212 — the redesign of FD2 actually delivers #212 rather than mooting it. Update the supersede note accordingly.
- `cortex/backlog/index.md`: regenerate via `just backlog-index` after status flips.

### Relevant existing patterns

- **Dual-source mirroring** (`justfile:621-669` `BUILD_OUTPUT_PLUGINS` / `build-plugin`): rsyncs `skills/`, `hooks/`, `bin/cortex-*` into `plugins/$p/`. Pre-commit drift hook (`.githooks/pre-commit`) enforces atomicity. New plugin-side artifacts must regenerate cleanly via `just build-plugin` or be gitignored.
- **Parity-check exceptions** (`bin/.parity-exceptions.md`): 5-column markdown table (script | category | rationale | lifecycle_id | added_date). Generated `_version.py` is not a `bin/cortex-*` script — not scanned by `bin/cortex-check-parity`. No allowlist entry needed.
- **Hatch build configuration**: `[tool.hatch.build.targets.wheel]` and `[tool.hatch.build.targets.wheel.force-include]` already in pyproject. Adding `[tool.hatch.version]` and `[tool.hatch.build.hooks.vcs]` are additive sister-sections.
- **Sandbox-write conventions**: `cortex init` adds `cortex/` umbrella to `sandbox.filesystem.allowWrite`. `$TMPDIR` is in the global allowlist — no expansion needed for FD4's tmpdir-scoped real-install test.
- **Integration-test fixturing for `uv tool install`**: `tests/test_no_clone_install.py:113-144` (`_install_wheel_isolated`) and `tests/test_mcp_auto_update_orchestration.py:1116-1158` are canonical. Both set `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` to `tmp_path` subdirs and prepend to `PATH`. Both gracefully skip on egress-blocked sandboxes via the "Tokio executor failed" / "system-configuration" detection at `tests/test_no_clone_install.py:84-92`. Both use `@pytest.mark.slow`. Marker registered at `pyproject.toml [tool.pytest.ini_options] markers`.
- **NDJSON audit + sentinel pattern**: `_append_error_ndjson` at `server.py:798-852` (R14) and `_write_install_failed_sentinel` at `:373-396` (R4d) are reusable verbatim. The new version-mismatch branch reuses `stage="first_install"` convention OR registers a new sibling stage.

### Integration points and dependencies

- **`plugins/` ↔ `cortex_command/` at build time**: the wheel from `uv build --wheel` ships ONLY `cortex_command/` (per `pyproject.toml [tool.hatch.build.targets.wheel] packages = ["cortex_command"]`). `plugins/` is NOT in the wheel. So any "build-time" plugin artifact must materialize at **commit time** (`.githooks/pre-commit`) or **tag time** (`.github/workflows/release.yml`) — separately from the wheel build.
- **Marketplace-git-clone distribution**: per `.claude-plugin/marketplace.json:24-29`, plugins are sourced via relative paths into the cortex-command repo. Claude Code's marketplace fast-forwards a git clone at `~/.claude/plugins/marketplaces/cortex-command/`. Whatever is committed at the tag SHA is what ships. The plugin "build" is `git fetch`.
- **MCP-tool-call call path** (full chain Acceptance E needs to exercise): `claude-code MCP dispatch → plugin server.py FastMCP tool handler → _resolve_cortex_argv() → _ensure_cortex_installed() → [post-FD3: version comparison] → uv tool install --reinstall git+url@CLI_PIN[0] → verification via cortex --print-root → return argv → handler subprocess.run argv`. Mocked at `tests/test_no_clone_install.py:355-500` (Phase 3 doesn't traverse the new branch — see above).
- **CLI version reporting today vs post-fix**: `cortex --print-root --format json` is the only versioned surface; emits `{"version": "1.1", ...}` at `cli.py:225-232`. Three distinct version concepts (per `docs/release-process.md:19-23`): (1) pyproject `version` (package), (2) git tag (`v0.1.0`), (3) schema version (`CLI_PIN[1]`/`MCP_REQUIRED_CLI_VERSION`/envelope's `"version"` field). FD1 must not conflate (1) and (3).

### Conventions to follow

- **Dual-source enforcement**: new files under `plugins/cortex-overnight/` with source-of-truth elsewhere must be regenerable by `just build-plugin`; drift hook catches drift.
- **MUST-escalation policy** (CLAUDE.md:76-85): use soft positive-routing phrasing in `docs/internals/auto-update.md` and any rewritten #210 docs.
- **Solution horizon** (CLAUDE.md:64-67): the structural durable fix per this principle is the **CI-enforced consistency check** + hatch-vcs adoption — the bundled approach delivers the durable answer (eliminates the manual-step drift surface via CI feedback) without inventing a non-existent build step.
- **Kept user pauses parity**: §1a preflight (implement.md:90-101) is outside the inventory's tracked line range. Prose-only edits don't touch parity.
- **Events registry**: any new NDJSON `stage` value needs registration in `_NDJSON_ERROR_STAGES` at `server.py:772-780`.

## Web Research

### Prior art and reference implementations

**Dynamic versioning landscape**:
- **hatch-vcs** (https://github.com/ofek/hatch-vcs): canonical Hatch-backend choice; wraps setuptools-scm. Two-clause config: `[tool.hatch.version] source = "vcs"` + `[tool.hatch.build.hooks.vcs] version-file = "..."`. Build-time only — does NOT re-emit on editable installs.
- **setuptools-scm** (https://github.com/pypa/setuptools-scm): the de-facto PyPA tool; older, more battle-tested. hatch-vcs uses it internally.
- **uv-dynamic-versioning** (https://github.com/ninoseki/uv-dynamic-versioning): newer, hatchling-based, recommended by pydevtools handbook for *new* uv projects; existing hatch-vcs setups are fine as-is.
- **versioningit**: alternative with more configurable tag-to-version transforms; less common.

**Two-layer host/plugin compatibility patterns (analogues)**:
- **Terraform `required_version`** (https://developer.hashicorp.com/terraform/language/expressions/version-constraints): plugin/module declares constraint, host parses with version-comparison library, acts on mismatch. Closest analogue.
- **VS Code `engines.vscode`**: host refuses to install extension whose engine constraint isn't met. Install-time, not runtime.
- **.NET `dotnet-tools.json`**: pinned plain-version-string per tool; reproducibility via `dotnet tool restore`. No constraint syntax.
- **GitHub Actions `uses: action@vN`**: floating-major or SHA-pin per org policy.

The Terraform/VS Code patterns are the closest fit for `_ensure_cortex_installed`: plugin declares CLI_PIN, host parses with `packaging.version`, acts on mismatch. The gap is that the constraint exists but the comparison branch was never wired.

### Relevant documentation and key takeaways

- **PEP 440** (https://peps.python.org/pep-0440/): `Version("v0.1.0") == Version("0.1.0")` — leading `v` is normalized away. `packaging.utils.canonicalize_version("v0.1.0")` returns the bare form.
- **packaging.version.Version** (https://packaging.pypa.io/en/stable/version.html): supports `<`, `<=`, `==`, `>=`, `>`, `!=`. Raises `InvalidVersion` on non-PEP-440. The single-line idiom: `Version(installed) < Version(required)`.
- **importlib.metadata** (https://docs.python.org/3/library/importlib.metadata.html): works inside the venv where the wheel is installed. Wrap in `try/except PackageNotFoundError` with sentinel fallback. The canonical idiom (Adam Johnson, https://adamj.eu/tech/2025/07/30/python-check-package-version-importlib-metadata-version/):
  ```python
  try:
      __version__ = importlib.metadata.version("cortex-command")
  except importlib.metadata.PackageNotFoundError:
      __version__ = "0.0.0"  # editable/source fallback
  ```
- **hatch-vcs `_version.py` semantics**: build-time only. Default tag pattern accepts `v1.0.0`, `1.0.0`, `project-v1.0.0`. `[tool.hatch.version.raw-options] local_scheme = "no-local-version"` avoids PEP-440-local-version suffixes (`+gabc1234`) on dirty checkouts. `.gitignore` the generated file.
- **uv tool install upgrade**: no `@latest` for git URLs. Must pass explicit tag + `--force`/`--reinstall`. Canonical incantation: `uv tool install --from git+...@vX.Y.Z --force <name>`.
- **uv tool list --outdated** (https://iamlyx.com/en/stem/uv-tool-name-collision/): **known to lie for git-installed packages**. Do not rely on it for the version-comparison gate.

### Known patterns and anti-patterns

**Do**:
- `dynamic = ["version"]` in `[project]`, source from `[tool.hatch.version] source = "vcs"`.
- Wrap `importlib.metadata.version(...)` in `try/except PackageNotFoundError` with sentinel fallback.
- Use `packaging.version.Version` for comparison. Never compare version strings lexically.
- For CLI_PIN destined to match a CLI version, store the *bare PEP 440 form* (`"0.1.0"`), not the git-tag form — both parse via `Version()`, but bare form avoids confusion in `==` string comparisons elsewhere. (Note: ticket currently uses `"v0.1.0"`; spec must decide whether to migrate or normalize at comparison time.)
- For tests exercising `uv tool install` end-to-end: set `UV_TOOL_DIR`, `UV_CACHE_DIR`, optionally `UV_PYTHON_INSTALL_DIR` to `tmp_path` subdirs.

**Don't**:
- Commit the hatch-vcs-generated `_version.py` — desynchronizes from git state, breaks hatch-vcs assumptions.
- Rely on `uv tool list --outdated` for git-installed tools (broken).
- Compare versions with `str ==` or split-on-dot — handles `0.10.0` vs `0.9.0` incorrectly.
- Try to make `importlib.metadata.version` work for editable installs without `uv build` — accept the fallback path.
- Bake version literals into multiple files.

### Sources

- [hatch-vcs](https://github.com/ofek/hatch-vcs), [hatch-vcs footgun](https://github.com/maresb/hatch-vcs-footgun-example)
- [setuptools-scm](https://github.com/pypa/setuptools-scm)
- [uv-dynamic-versioning](https://github.com/ninoseki/uv-dynamic-versioning)
- [pydevtools: dynamic versioning for uv](https://pydevtools.com/handbook/how-to/how-to-add-dynamic-versioning-to-uv-projects/)
- [PEP 440](https://peps.python.org/pep-0440/), [packaging docs](https://packaging.pypa.io/en/stable/version.html)
- [importlib.metadata](https://docs.python.org/3/library/importlib.metadata.html), [Adam Johnson on importlib.metadata](https://adamj.eu/tech/2025/07/30/python-check-package-version-importlib-metadata-version/)
- [Armin Ronacher: Python Packaging Metadata](https://lucumr.pocoo.org/2024/11/26/python-packaging-metadata/), [uv issue #6860](https://github.com/astral-sh/uv/issues/6860), [uv issue #9936](https://github.com/astral-sh/uv/issues/9936)
- [uv tools concepts](https://docs.astral.sh/uv/concepts/tools/), [uv tools guide](https://docs.astral.sh/uv/guides/tools/)
- [Lyx on uv tool list --outdated bug](https://iamlyx.com/en/stem/uv-tool-name-collision/)
- [Terraform required_version](https://developer.hashicorp.com/terraform/language/expressions/version-constraints)
- [VS Code engines.vscode](https://code.visualstudio.com/api/references/extension-manifest)
- [.NET dotnet-tools.json](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-tool-install)

## Requirements & Constraints

### Relevant requirements from `cortex/requirements/project.md`

- **Distribution (Overview, line 7)**: "Ships CLI-first as a non-editable wheel: `uv tool install git+<url>@<tag>`." → fixes install mode; FD4 test exercises wheel path only.
- **Handoff readiness (Philosophy of Work, line 13)**: "criteria are agent-verifiable from zero context" → Acceptance E (live release on maintainer's machine) **violates this principle**. FD4 is the spec-required substitute. See "Considerations Addressed" below.
- **Complexity (line 19)**: "Must earn its place by solving a real problem now. When in doubt, simpler wins." → bears on the FD2 redesign — CI lint is structurally simpler than build-time generation.
- **Solution horizon (line 21)**: "Long-term project — fixes reflect that. Before suggesting a fix, ask: do I already know this needs redoing... If yes, propose the durable version or surface both with tradeoff." → bundled fix is durable; the FD2 redesign (CI lint) is durable AND simpler than the ticket's proposed approach.
- **Quality bar (line 23)**: "Tests pass; the feature works as specced. ROI matters — ship faster, not be a project."
- **File-based state (line 27)**: plain files only. Generated `_version.py` is consistent.
- **Per-repo sandbox registration (line 28)**: "the only write cortex-command makes in `~/.claude/`" → FD4's tmpdir test must not expand `~/.claude/` write surface. `$TMPDIR` is already in global allowWrite.
- **SKILL.md-to-bin parity (line 29)**: new `bin/cortex-*` scripts trigger parity. No new bin scripts in this ticket — only generated `_version.py` (not parity-scanned).
- **Defense-in-depth for permissions (Quality Attributes, line 38)**: rely on allow/deny enforcement for sandbox-excluded commands like `uv tool install`.
- **Project boundaries / Out of Scope (line 55)**: "Published packages or reusable modules for others — out of scope; cortex ships as a non-editable wheel." → confirms wheel-install-only scope.
- **Conditional Loading (lines 62-67)**: no area docs matched for tags `[mcp, upgrade, internals, plugin]`. `project.md` only.

### Relevant requirements from `cortex/requirements/pipeline.md`

- **Pre-install in-flight guard (Dependencies, line 154)**: "`cortex` aborts when an active overnight session is detected (phase != `complete` AND `verify_runner_pid` succeeds); bypassable inline via `CORTEX_ALLOW_INSTALL_DURING_RUN=1` (do NOT export). Carve-outs: pytest, runner-spawned children (`CORTEX_RUNNER_CHILD=1`), dashboard, cancel-force invocation." → **directly relevant to FD3**: R4's version-compare branch must honor this guard. **Critical gap** (Adversarial §1.B): the plugin can't import `cortex_command.install_guard` (different interpreter); the guard logic must be reimplemented inline in the plugin.

### Relevant requirements from `CLAUDE.md`

- **Overnight docs source of truth (Conventions, line 50)**: pattern is "owning doc + cross-link, don't duplicate." `docs/internals/auto-update.md` becomes a sibling owning doc.
- **Memory vs durable fixes (line 54)**: rewriting #210 docs > capturing the gap in memory.
- **Solution horizon (line 66)**: "A deliberately-scoped phase of a multi-phase lifecycle is not a stop-gap." → bundled #213 is the durable phase, not a stop-gap.
- **Design principle: prescribe What and Why, not How (lines 68-74)**: internals doc should describe decisions/gates/intent, not procedure.
- **Skill/phase authoring (line 62)**: prefer structural separation over prose-only enforcement → CI lint > documentation-only "remember to bump CLI_PIN."
- **MUST-escalation policy (lines 76-84)**: new authoring uses soft positive-routing; pre-existing MUST grandfathered.

### Architectural constraints by Fix Direction

| Fix Direction | Constraint | Source |
|---------------|------------|--------|
| FD1 (hatch-vcs) | Non-editable wheel distribution; durable fix per Solution horizon | project.md:7, 21, 55 |
| FD2 (CLI_PIN — redesigned to CI lint) | Plain-file state; structural enforcement > prose | project.md:27; CLAUDE.md:62 |
| FD3 (R4 version-compare) | In-flight guard must be honored; defense-in-depth for permissions | pipeline.md:154; project.md:38 |
| FD3 | Destructive ops preserve uncommitted state | project.md:39 |
| FD4 (real-install test) | Pytest carve-out from in-flight guard; no `~/.claude/` write expansion | pipeline.md:154; project.md:28 |
| FD5 (internals doc) | Overnight docs source-of-truth pattern; soft positive-routing | CLAUDE.md:50, 76-84 |
| FD6 (rewrite #210 docs) | Soft positive-routing; What/Why not How | CLAUDE.md:68-84 |
| FD7 (close #211/#212) | File-based state in backlog markdown | project.md:27 |

### Scope boundaries

- **Wheel-install only**: no editable-install support needed; integration test exercises wheel path.
- **Out of scope**: dotfiles/machine configuration (belong in machine-config); cross-repo work in one overnight session.
- **`~/.claude/` write surface**: only `cortex init`'s settings.local.json sandbox entry — no additional writes.

## Tradeoffs & Alternatives

### Axis 1: Dynamic versioning system

| Option | Pros | Cons |
|--------|------|------|
| **hatch-vcs** (recommended for CLI) | PyPA-org, drop-in for hatchling, one-clause config | Needs git history at build time; PEP 440 ≠ git tag form |
| setuptools-scm | De-facto standard | Strict superset of hatch-vcs (which wraps it); no upside |
| uv-dynamic-versioning | Recommended for new uv projects | New, less battle-tested; hatch-vcs is fine |
| Committed `_version.py` written by release script | No build-time git dep | Same human-reliability gap; mandates release-time discipline |
| Runtime `git describe` | Always reflects checkout | **Fails under wheel install** — no .git tree |

**Recommended**: hatch-vcs for CLI. The other options either fail under wheel install or replay the manual-step bug.

### Axis 2: CLI_PIN propagation mechanism (PLUGIN-SIDE)

**This is where the ticket's framing breaks down.** Plugin ships as marketplace git clone, NOT a built wheel. No build-time hook.

| Option | Pros | Cons |
|--------|------|------|
| **Manual edit + CI lint** (recommended; replaces ticket FD2) | Works with marketplace-git-clone; conspicuous CI failure signal | Manual step still exists, but now CI-enforced |
| Build-time `_version.py` generation (ticket text) | None, given no plugin build step | Architecturally non-viable; bootstrap paradox |
| Committed file edited by release script | Works with marketplace-clone | Same manual-step reliability gap unless CI-gated |
| Read from CHANGELOG / `.cortex-version` text | Single source-of-truth maintainer already edits | Adds parsing fragility; startup IO |
| Read from installed-cortex's importlib.metadata | Eliminates the constant | **Plugin's interpreter ≠ CLI's interpreter** under uv tool install — won't find it |
| Plugin commit SHA → installed CLI commit SHA | Immutable; no normalization | Loses semver; loses upgrade signal |

**Recommended**: keep the `CLI_PIN` literal at `server.py:105` (or move to a `.cli-pin` text file — moral equivalent), add a CI lint on tag push in `.github/workflows/release.yml` that fails the release on mismatch with `git describe --tags HEAD`. Plus `tests/test_release_artifact_invariants.py` for pre-CI catch. This delivers the structural value (conspicuous CI feedback) without the build-step fiction.

### Axis 3: Plugin distribution context

Already addressed in Axis 2 — marketplace-git-clone forces the redesign.

### Axis 4: Version-comparison API (R4 hot path)

| Option | Pros | Cons |
|--------|------|------|
| **`cortex --print-root --format json["package_version"]`** (recommended, post-FD1) | Reuses existing subprocess; existing post-install verification already calls it | Requires new envelope field (additive minor bump) |
| `importlib.metadata.version("cortex-command")` from plugin | In-process, microseconds | **Won't find cortex-command in plugin's ephemeral uv-run venv** |
| `cortex --version` (after wiring) | Smaller output | One more entry point; no advantage over --print-root |
| `pip show cortex-command` | None | Strictly worse |

**Recommended**: D1 with a NEW `package_version` envelope field. The existing `version` field stays as the schema envelope version. R4 reads `payload["package_version"]`, parses with `packaging.version.Version`, compares to `CLI_PIN[0]` (normalized via leading-v strip OR symmetric Version parse).

### Axis 5: Tag normalization

| Option | Pros | Cons |
|--------|------|------|
| Strip leading `v` (`CLI_PIN[0].lstrip("v") == installed_version`) | One line, simple equality | String comparison only; no `<` semantics |
| Store PEP 440 in CLI_PIN, add "v" at install-time | Internal rep matches importlib.metadata | Diverges from existing release-process.md docs |
| **`packaging.version.Version` symmetric parse** (recommended) | Robust to dev/local-version suffixes; supports `<`/`>=` | Requires `packaging` in plugin PEP 723 deps |

**Recommended**: E3. Add `packaging` to the plugin's PEP 723 dependency declaration. The `_parse_major_minor` function at `server.py:124` is currently brittle to PEP 440 — replacing it with `Version`-based comparison hardens it.

### Axis 6: Acceptance test approach

| Option | Pros | Cons |
|--------|------|------|
| **Real `uv tool install` in tmpdir** (recommended; ticket FD4) | Catches Gap C end-to-end; highest fidelity | Slow (15-60s); requires uv on runner; network-touching unless offline-able |
| Hermetic mock with subprocess.run patched | Fast, deterministic | **This is what existing tests do — missed Gap C** |
| Golden-trace record/replay | Fast playback | Snapshots go stale as uv evolves |
| Partial integration (real flock, mocked install) | Exercises FS side-effects | Misses "does CLI version actually change?" — the Gap C signal |

**Recommended**: F1 marked `@pytest.mark.slow` + `@pytest.mark.serial`, gated on `uv` availability. Existing mocked tests retained as fast regression nets. NOT either-or.

### Axis 7: Bundling vs splitting

User has confirmed bundling all 7. Surfaced for completeness:

- **Blast radius**: ~8-12 file modifications across 4 categories (build, plugin, CLI, docs/tests). Dense PR but reviewable.
- **Reverse-out cost**: hatch-vcs adoption (FD1) is the highest-risk piece. Two-tag landing (FD1 alone first, soak for one session-start, then FD2-7) reduces risk but adds a tag. **Surfaced to user via spec phase complexity/value gate**.
- **Test interdependence**: FD4 needs FD1+2+3 wired to assert acceptance D. FD5/6/7 are cleanly separable.

### Recommended overall approach

1. **FD1**: hatch-vcs for CLI wheel + ADD `package_version` field to print-root envelope (additive, schema bump `"version": "1.2"`). Preserve envelope-version semantic.
2. **FD2 (redesigned)**: keep `CLI_PIN` literal at `server.py:105`; add CI lint in `release.yml` + `tests/test_release_artifact_invariants.py`. Subsume #212 (the lint is morally what #212 wanted).
3. **FD3**: wire version-compare branch in `_ensure_cortex_installed` reading `payload["package_version"]` via `packaging.version.Version`. Inline session-detection guard (no install_guard.py import). Add `packaging` to plugin PEP 723 deps.
4. **FD4**: real-install test in tmpdir; three test phases including the active-session-abort and R13-on-wheel-install paths.
5. **FD5**: author `docs/internals/auto-update.md` with audit table.
6. **FD6**: rewrite #210 docs; include the stale-tag literals at `install.sh:41` and `docs/setup.md:27`.
7. **FD7**: supersede #211 and #212.

## Adversarial Review

(Synthesized from Agent 5; full content surfaced via the Open Questions and Tradeoffs sections above. Key irreducible findings:)

### Failure modes and edge cases

- **A. `.cli-pin` text file vs `_version.py` is the same human-reliability bug renamed.** The CI lint is the actual value-add; the file format is secondary. (Drives FD2 redesign.)
- **B. R4 reinstall under in-flight guard**: `_ensure_cortex_installed`'s reinstall branch currently DOES NOT consult `check_in_flight_install` — install_guard.py is in cortex_command/ which is not importable from the plugin's PEP 723 venv. R4 silently rewrites the running CLI mid-overnight-run. Real correctness bug FD3 must NOT inherit. (Drives FD3 inline-guard requirement.)
- **C. `_check_version` rejects PEP 440 versions**: `_parse_major_minor` at `server.py:131` splits on `"."` `maxsplit=1` and `int()`-coerces both halves. `"1.0.3"` → `int("0.3")` → ValueError. Naively rewiring `cli.py:226` to `importlib.metadata.version` breaks every `_check_version` consumer. (Drives the envelope vs package_version split.)
- **D. Acceptance E proxy is materially weaker than the bare claim**: FD4 exercises cortex-command-side mismatch detection only. Marketplace fast-forward cadence, tag-not-yet-on-origin race (Fix 2 redesign vs original ticket text), force-pushed-tag identity collision, session-restart-vs-mid-session timing — all unexercised.
- **E. R13 schema-floor + hatch-vcs major bump**: if a future tag is `v2.0.0`, `MCP_REQUIRED_CLI_VERSION` stays "1.0" → R13 fires synchronously, but the wheel-install short-circuit at `server.py:1561` returns silently. Silent-degraded mode. Replace with stderr surface.
- **F+G. Test coverage gaps**: existing tests patch `shutil.which → None`, never traversing the new version-compare branch. Existing `test_schema_floor_triggers_synchronous_upgrade` `.git/.mkdir`s, bypassing the wheel-install dormancy path R4 is supposed to back-stop.

### Security concerns

- **H. Mutable-tag race + uv cache reuse**: `uv tool install --reinstall git+url@tag` may reuse cached wheel of the same tag string when the tag is force-pushed. Mitigation: append commit SHA or `uv cache clean cortex-command` before reinstall.
- **I. PATH-poisoning under reinstall verification**: post-install probe calls bare `cortex` via PATH. Mitigation: capture absolute path from `uv tool install` output.
- **J. PEP 440 local-version suffixes** (`1.0.3+gabc1234.d20260513`) trip `_parse_major_minor`. Mitigation: `packaging.version.Version`, set `local_scheme = "no-local-version"` in `[tool.hatch.version.raw-options]`.
- **K. `fetch-depth=1` in release.yml breaks hatch-vcs**: needs `fetch-depth: 0` + `fetch-tags: true`.

### Assumptions that may not hold

- **M. Confirmed**: plugin's interpreter ≠ CLI's interpreter under `uv tool install`. `importlib.metadata.version("cortex-command")` from plugin process raises `PackageNotFoundError`. Subprocess shelling `cortex --print-root` is structurally required by the R1 architectural invariant.
- **N. Envelope-version ≠ package-version semantic**: cli.py:226's `"version": "1.1"` is the JSON envelope schema version per its docstring at :166-170, NOT the package version. Five consumers depend on the `"M.m"` shape. Naively rewiring breaks all five.
- **O. FD4 ≠ Acceptance E**: the marketplace layer is entirely unmocked by FD4.
- **P. User's "bundle all 7" decision should be re-surfaced at spec phase**: the cascading complexity (envelope/package split, in-flight guard inheritance gap, FD2 redesign) wasn't visible at clarify.

### Recommended mitigations (top items, integrated into spec direction)

1. Replace ticket FD2 (`_version.py` generation) with CI lint in release.yml + pre-CI invariant test.
2. Split FD1 into 1a (additive `package_version` field) + 1b (hatch-vcs adoption with envelope preserved).
3. FD3 must include inline session-detection guard (no `install_guard.py` import).
4. FD4 must add: active-session-abort phase, R13-on-wheel-install phase, version-mismatch-fires-reinstall phase.
5. `fetch-depth: 0` + `fetch-tags: true` in release.yml.
6. Expand FD6 to `install.sh:41` and `docs/setup.md:27` stale-tag literals.
7. Re-surface bundle scope to user at spec §4 complexity/value gate.
8. Acceptance E re-scoping: documented residual risk, partial FD4 coverage.
9. `packaging.version.Version` for plugin-side comparison. Add `packaging` to PEP 723 deps.
10. R13-on-wheel-install: replace silent short-circuit with stderr surface.

## Open Questions

These need spec-phase resolution before Plan can be written. Some require user input; others can be locked by the structured interview.

**(a) Envelope-version vs package-version contract (HIGH PRIORITY — drives FD1 and FD3 wiring)**
- Adversarial §1.C and §3.N surfaced: cli.py:226's `"version": "1.1"` is the JSON envelope schema version (per docstring at :166-170), NOT the package version. Naively rewiring it to `importlib.metadata.version()` breaks 5 consumers (`_check_version`, `_schema_floor_violated`, `_JSON_SCHEMA_VERSION` at `cortex_command/overnight/cli_handler.py:113,116`, etc.).
- **Proposed resolution**: split FD1 into 1a (additive `package_version` field, envelope `version` bumps 1.1 → 1.2 per R16) + 1b (hatch-vcs adoption). R4 reads `payload["package_version"]`, `_check_version` continues reading `payload["version"]`.
- **Spec must confirm** this contract with the user (and decide whether `package_version` should be a string field, a structured `{major, minor, patch}` object, or canonicalize through `packaging.version`).

**(b) FD2 redesign (CI lint vs build-time generation)**
- Adversarial §1.A and §1.L surfaced: build-time `_version.py` generation for the plugin is architecturally non-viable under marketplace-git-clone distribution. No plugin build step exists.
- **Proposed resolution**: keep `CLI_PIN` literal at `server.py:105`; add CI lint in release.yml + pre-CI invariant test that compares `CLI_PIN[0]` to `git describe --tags HEAD` on tag-named commits.
- **Spec must confirm** the user accepts this redesign — it materially changes what FD2 delivers (CI gate, not auto-generation) while delivering the same structural value (conspicuous CI feedback eliminates the manual-step drift).

**(c) In-flight guard inheritance gap in FD3**
- Adversarial §1.B surfaced: R4's reinstall branch currently does NOT consult `check_in_flight_install` because `install_guard.py` is in `cortex_command/` (not importable from the plugin's PEP 723 venv). The new version-compare branch must inline session-detection.
- **Proposed resolution**: spec adds an inline session-check helper to the plugin that reads `~/.local/share/overnight-sessions/active-session.json`, verifies runner pid via `/proc` lookup (no psutil dep), honors `CORTEX_ALLOW_INSTALL_DURING_RUN=1` and `CORTEX_RUNNER_CHILD=1`.
- **Spec must decide**: should this be a pre-FD3 standalone fix (the existing reinstall branch ALSO inherits the bug), or bundled with FD3?

**(d) Bundling vs two-tag landing strategy**
- Tradeoffs Agent 4 surfaced: hatch-vcs adoption is the highest-risk piece. A two-tag landing (FD1 alone first, observe wheel-name correctness across one session-start, then FD2-7 in next tag) reduces reverse-out risk.
- User confirmed "bundle all 7" at clarify, but did not see the cascading complexity surfaced post-research.
- **Spec §4 complexity/value gate should re-surface this** with the new information.

**(e) Acceptance E re-scoping**
- Per project.md:13 ("agent-verifiable from zero context") and Adversarial §1.D / §3.O: Acceptance E (live release on maintainer's machine) is formally non-agent-verifiable. FD4 covers cortex-command-side mismatch detection but does NOT exercise the marketplace fast-forward layer, tag-not-yet-on-origin race, or force-pushed-tag identity collision.
- **Proposed resolution**: spec downgrades Acceptance E to "documented residual risk — manual maintainer smoke verification." Adds `tests/test_release_artifact_invariants.py` (CI invariant: `git describe --tags` == `CLI_PIN[0]` at tag-named commits) as the partial proxy.
- **Spec must confirm** this re-scoping with the user.

**(f) Stale-tag literal coverage in FD6**
- Adversarial §1.Q surfaced: ticket FD6 enumerates `implement.md` but misses `install.sh:41` and `docs/setup.md:27` (Quickstart fence).
- **Spec must enumerate**: run `git grep '@v[0-9]'` to find every stale tag literal; decide replacement strategy (parameterize via env var? literal-with-latest-tag?) for each.

**(g) R13 silent-degraded mode on wheel install**
- Adversarial §1.E surfaced: when R13 schema-floor fires under wheel install, the short-circuit at `server.py:1561` returns silently. The user sees no error and no upgrade path.
- **Proposed resolution**: spec adds a stderr surface (one-line message naming `uv tool install --reinstall` as the remediation).
- **Decision needed**: should this be part of FD3 (closely related to R4 wiring) or a sibling fix? Bundling argues yes; surface separately if it adds review burden.

**(h) `packaging` as plugin PEP 723 dependency**
- Plugin currently declares only `mcp` and `pydantic` in its PEP 723 header.
- Adopting `packaging.version.Version` for the comparison branch requires adding `packaging` to the dependency list.
- **Spec must confirm**: this is a small dep with no security concerns, but it does change the plugin's ephemeral venv footprint. Acceptable?

## Considerations Addressed

- **Acceptance E proxy criterion**: Research confirms the integration test in Fix Direction 4 is the leading agent-verifiable proxy, BUT material caveats apply (per Adversarial §1.D and §3.O): FD4 exercises the cortex-command-side mismatch detection only — the Anthropic-owned marketplace fast-forward layer, the tag-not-yet-on-origin race window (potentially WIDENED by an auto-derive approach in original FD2 text, ELIMINATED by the redesigned CI-lint approach), and force-pushed-tag identity collision are unexercised. Spec's resolution direction: (1) FD4 stays as the canonical agent-verifiable test (with three additional phases: active-session-abort, R13-on-wheel-install, version-mismatch-fires-reinstall); (2) Acceptance E is re-scoped to "documented residual risk — manual maintainer smoke"; (3) a new `tests/test_release_artifact_invariants.py` provides a CI-time invariant check (`git describe --tags == CLI_PIN[0]` at tag-named commits) as a structural partial proxy that closes the tag-not-yet-on-origin window at release-tagging time.
