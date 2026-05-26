[← Back to Agentic Layer](../agentic-layer.md)

# Auto-update Architecture

**Internal reference — not a user-facing skill.** For the user-facing summary, see [`docs/setup.md#upgrade--maintenance`](../setup.md#upgrade--maintenance).

This doc is the authoritative source-of-truth for how the cortex-overnight plugin and the cortex CLI stay version-coupled. It synthesizes the three-layer architecture (Claude Code marketplace clone + MCP-tool-call-gated CLI reinstall + SessionStart-async-gated CLI reinstall), the load-bearing component map, the trust model, the release ritual end-to-end, and an Intent vs currently-wired audit. Sibling docs in this directory ([`mcp-contract.md`](mcp-contract.md), [`pipeline.md`](pipeline.md), [`sdk.md`](sdk.md)) cover adjacent contracts and module internals; this doc owns the auto-update flow itself.

---

## Intent

Cortex-command ships as two halves that must stay paired in version: the `cortex-overnight` plugin (refreshed by Claude Code's marketplace mechanism) and the `cortex` CLI (installed via `uv tool install` and refreshed by `uv tool install --reinstall`). The user-visible promise is that turning on "Auto-Update Marketplace Plugins" in Claude Code is the only manual step a user takes — the plugin and the CLI stay in lockstep without further intervention. A new release shipped to the upstream repository propagates to the user's machine within one Claude Code session-restart plus one MCP tool call.

The architecture is structured so the user never has to reason about which half is stale. The plugin carries an embedded `CLI_PIN` constant naming the CLI tag it expects; the next MCP tool call after a plugin refresh observes the mismatch between the installed CLI version and `CLI_PIN[0]` and runs `uv tool install --reinstall` synchronously before delegating to the CLI. The schema-floor check at `_schema_floor_violated` (see [Component map](#component-map)) hard-rejects any payload whose major schema-version differs from the plugin's baked-in floor, so a paired-but-incompatible plugin/CLI combination surfaces as an actionable remediation message rather than silent miscomputation.

The auto-update flow was originally MCP-tool-call-gated on the **execution** side, but Layer 3 (the SessionStart-async-gated reinstall) now closes the execution gap for daytime-only users who never invoke an MCP tool. The visibility-only `cortex-cli-version-sync.sh` SessionStart hook (#235) continues to emit `additionalContext` on drift so Claude warns about stale bare-shell `cortex …` calls during the ~5–300 second async install window. The `implement.md §1a` preflight remains a fail-fast diagnostic for any drift that survives both hooks (dev-mode skips, throttle-window invocations, hook regressions, sentinel'd install failures). See the [Bash-tool carve-out](#bash-tool-subprocess-carve-out) below for the narrowed residual risk and the [Trust model](#trust-model) section for the supply-chain implications of widening from MCP-call-gated to SessionStart-gated reinstall.

---

## Three-layer architecture

Upgrades happen in three layers, and it helps to keep them mentally distinct because Claude Code owns the first layer and cortex-command owns the second and third.

### Layer 1: marketplace fast-forward at Claude Code startup

When Claude Code launches, the plugin marketplace mechanism refreshes the local clone of the plugin repository (including the `cortex-overnight` server module that carries the `CLI_PIN` constant). This is the layer where a `CLI_PIN` bump arrives on the user's machine. Claude Code controls this layer end-to-end; cortex-command does not. The marketplace's fast-forward semantics — force-pushed-tag handling, session-restart timing, tag-not-yet-on-origin race — are Anthropic-owned and treated as residual risk from this doc's perspective.

A user who disables marketplace auto-updates pins the embedded `CLI_PIN` to whatever tag was current at plugin install time. Schema versions still match between the embedded `CLI_PIN[1]` and the installed CLI's print-root envelope, so a stale-but-self-consistent plugin/CLI pair keeps working — the user just stays at the older version until they manually refresh the plugin.

### Layer 2: MCP-tool-call-gated CLI reinstall

The next time the `cortex-overnight` MCP server is invoked (e.g., `overnight_start_run`, `overnight_status`), the entry-point helper `_resolve_cortex_argv` calls `_ensure_cortex_installed` (see [Component map](#component-map)) before delegating to the CLI. That function runs the first-install check and the version-comparison reinstall check; on mismatch, it acquires a flock, delegates the install proper to `install_core._run_install_and_verify` (which runs `uv tool install --reinstall --refresh-package cortex-command git+<url>@CLI_PIN[0]` and verifies via the absolute-path-pinned `cortex --print-root --format json` probe). The MCP server owns this layer end-to-end and does not import the cortex Python package — its sole interface to the CLI is the subprocess + JSON contract documented in [`mcp-contract.md`](mcp-contract.md).

The reinstall fires only under `uv tool install`-style wheel installs. Editable installs from a `cortex/` development clone short-circuit the reinstall branch via skip predicates (`CORTEX_DEV_MODE=1`, dirty working tree, non-`main` branch), since the dogfooding case wants `pip install -e .` semantics and the user manages CLI versions directly.

### Layer 3: SessionStart-async-gated CLI reinstall

For users on daytime-only workflows (skill prose, Bash `cortex …`, hooks under `claude/hooks/`, plugin-mirrored bin scripts) who never invoke a cortex-overnight MCP tool, Layer 2 never fires and the CLI stays stale indefinitely. Layer 3 closes that execution gap: the `cortex-cli-background-install.sh` async SessionStart hook (registered with `"async": true` in `hooks.json`) probes `CLI_PIN[0]` against the installed CLI on drift and, when warranted, calls `install_core.run_install_in_background()` to detach a `uv tool install --reinstall --refresh-package cortex-command git+<url>@CLI_PIN[0]` subprocess via `subprocess.Popen(..., start_new_session=True, stdin=DEVNULL, ...)`. The hook script itself exits in <2s; the detached install runs in the background for ~5–300 seconds depending on cache state.

The hook always detaches via `start_new_session=True` for uniform behavior across Claude Code versions: newer clients (v2.1.139+) honor `"async": true` and run the hook in background (detach is a no-op for correctness); older clients silently ignore the field but the detach still prevents launcher freeze per Anthropic Issue #43123. Skip-predicate parity with Layer 2 is preserved: `CORTEX_DEV_MODE=1`, dirty tree (narrowed to cortex-command repo only — see Requirement 26), non-`main` branch, and `CORTEX_AUTO_INSTALL=0` all silent-skip. An under-lock version re-check ensures that three concurrent SessionStarts result in one actual `uv tool install` invocation, not three. The install proper, the flock acquisition, the install-in-progress marker file, and the NDJSON audit stages (`session_start_drift_detected`, `session_start_reinstall`, `session_start_reinstall_under_lock_skip`, etc.) all live in `install_core.py` and are shared with Layer 2.

### Bash-tool subprocess carve-out

Bash-tool subprocess dispatches that shell out to `cortex …` directly — without going through the MCP server — do **not** trigger the Layer 2 reinstall. This is an intentional execution-side gap: routing every CLI subprocess through the MCP server would require either Claude Code-side instrumentation or a CLI-side phone-home, both of which violate the plugin-imports-zero-cortex-modules contract.

Before Layer 3, the gap was bracketed only by visibility closure: the `cortex-cli-version-sync.sh` SessionStart hook (#235) probes the installed CLI against `CLI_PIN[0]` once per 30-minute throttle window and emits `additionalContext` to Claude on drift, so the next bare-shell `cortex …` call is preceded by a warning that names the expected and installed versions and the manual `uv tool install --reinstall --refresh-package cortex-command git+…@<tag>` remediation. The hook honors the same skip predicates as `_evaluate_skip_predicates` (`CORTEX_DEV_MODE=1`, dirty tree, non-`main` branch) so dogfooding sessions are not warned about expected drift.

Layer 3 now closes the execution gap for daytime-only users: the async install hook fires on SessionStart and reinstalls in the background without waiting on any MCP tool call. Only Bash-tool subprocesses fired during the ~5–300 second install window remain at risk — a `cortex …` call that races the in-flight async install may execute against a partially-overwritten venv. The sync hook's `additionalContext` warns about prior-session installs (R24) so users in fresh sessions opened during another session's install window receive a heads-up. The `implement.md §1a` preflight remains the fail-fast diagnostic for any drift that survives both hooks (dev-mode skips, throttle-window invocations, hook regressions, install failures sentinel'd within the 30-minute retry window).

---

## Component map

Each row names a load-bearing component, its file:line, and a one-sentence role.

| Component | Location | Role |
|---|---|---|
| `CLI_PIN` | `plugins/cortex-overnight/server.py:106` | Embedded `(tag, schema_version)` tuple pairing the plugin with a specific cortex CLI tag and schema major; derived `MCP_REQUIRED_CLI_VERSION` lives at `plugins/cortex-overnight/server.py:113`. |
| `_resolve_cortex_argv` | `plugins/cortex-overnight/server.py:973` | Entry-point helper that wraps every cortex subprocess invocation; calls `_ensure_cortex_installed` at `plugins/cortex-overnight/server.py:986` before returning the argv. |
| `_ensure_cortex_installed` (R4) | `plugins/cortex-overnight/server.py:775` | First-install + version-mismatch reinstall orchestrator; the heart of Layer 2. |
| `_maybe_check_upstream` (R8, legacy) | `plugins/cortex-overnight/server.py:1252` | Legacy editable-install path that runs upstream-advance checks; superseded by `_ensure_cortex_installed` for wheel installs. |
| `_schema_floor_violated` (R13) | `plugins/cortex-overnight/server.py:1827` | Schema-floor compatibility gate that hard-rejects payloads whose schema-version major differs from `MCP_REQUIRED_CLI_VERSION`; emits stderr remediation message on violation. |
| `_NDJSON_ERROR_STAGES` registry | `plugins/cortex-overnight/server.py:1095` | Allowlist of audit-stage values emitted by the reinstall branch; gates `version_mismatch_reinstall`, `version_mismatch_reinstall_parse_failure`, and `version_mismatch_blocked_by_inflight_session` records. |
| `cortex --print-root` envelope | `cortex_command/cli.py:232` | Versioned JSON payload carrying `version` (package version) and `schema_version` (envelope floor) — the bootstrap call MCP consumers parse. |
| `check_in_flight_install_core` | `cortex_command/install_guard.py:150` | Stdlib-only core that blocks reinstall when an overnight session is active; vendored as a byte-identical sibling at `plugins/cortex-overnight/install_guard.py:27`. |
| CI lint (defense-in-depth) | `.github/workflows/release.yml:28` | Hard-fails the release job when `CLI_PIN[0]` does not match the pushed tag; subsumes #212's drift-lint goal. |
| `cortex-cli-version-sync.sh` (#235) | `plugins/cortex-overnight/hooks/cortex-cli-version-sync.sh` | SessionStart drift-detector; regex-parses `CLI_PIN` from `cli_pin.py`, probes the installed CLI via `cortex --print-root --format json`, and emits `additionalContext` on drift. Visibility-only — does NOT reinstall. Honors a 30-minute freshness throttle and the same skip predicates as `_evaluate_skip_predicates`. Also surfaces prior-session install-in-progress markers and recent `session-install-failed.<ts>` sentinels in its `additionalContext`. |
| `install_core.py` | `plugins/cortex-overnight/install_core.py` | Stdlib-only sibling that owns `_run_install_and_verify`, flock helpers, marker-file handling, NDJSON audit emission, and `run_install_in_background()`. Called by both Layer 2 (`_ensure_cortex_installed`) and Layer 3 (`cortex-cli-background-install.sh`). Imports nothing from `cortex_command.*` and only stdlib + sibling `install_guard`/`cli_pin`; structurally enforced by `.githooks/pre-commit`. |
| `cortex-cli-background-install.sh` | `plugins/cortex-overnight/hooks/cortex-cli-background-install.sh` | Async SessionStart hook (`"async": true` in `hooks.json`); the heart of Layer 3. Bash trampoline that invokes a Python heredoc calling `install_core.run_install_in_background()`. Always-detach via `subprocess.Popen(..., start_new_session=True, stdin=DEVNULL)` for uniform behavior across Claude Code versions (newer: `async: true` honored; older: detach prevents launcher freeze per Issue #43123). Hook script exits in <2s regardless of install duration. Honors `CORTEX_AUTO_INSTALL=0`, `CORTEX_DEV_MODE=1`, and narrowed dirty-tree skip predicates. |

---

## Trust model

Layer 3 widens the supply-chain attack surface relative to Layers 1–2. Under the prior two-layer model, the cortex CLI was reinstalled only when a user explicitly invoked a cortex-overnight MCP tool — an action that is rare on daytime-only workflows and represents a deliberate, user-initiated event. Under the three-layer model, the reinstall fires automatically on every SessionStart that observes drift, with no per-install user action. The asymmetry matters because the trust anchor — the release tag `CLI_PIN[0]` points at — is mutable: a tag is a movable reference, not an immutable content hash.

### Force-push attack vector

A compromised maintainer account (stolen PAT, hijacked GitHub session, social-engineered force-push approval) can force-push a `vX.Y.Z` release tag to point at a malicious commit. On the next user SessionStart, the Layer 3 async hook observes `CLI_PIN[0]` still naming `vX.Y.Z` and the installed CLI matches — no drift detected, no reinstall, no exposure. But on the *next* legitimate release that bumps `CLI_PIN[0]`, Layer 1 fast-forwards the plugin clone (carrying the new tag name) and Layer 3 detects drift and runs `uv tool install --reinstall --refresh-package cortex-command git+...@<new-tag>`. The attack window is the period during which a force-pushed-and-malicious tag exists between the compromise and either a defender's force-push correction or the next legitimate release. Any user whose SessionStart fires during that window runs malicious code with the privileges of the user account running Claude Code.

### Immediate mitigation: GitHub Repository Rulesets

The repo-config-layer mitigation is to configure a **GitHub Repository Ruleset** on the cortex-command repo that **blocks force-pushes on tags matching `v*`**. This is an operator action — it lives in GitHub's UI under `Settings → Rules → Rulesets`, not in this codebase. Once enabled, the ruleset rejects force-push attempts at the GitHub API layer, neutralizing the force-push attack vector entirely (modulo GitHub-side compromise, which is out of scope for cortex-command's trust model). The ruleset must include `Restrict updates` and `Block force pushes` rules with a tag-pattern targeting `v*`.

The rest of the trust posture is layered as follows:

- **`CORTEX_AUTO_INSTALL=0` per-user opt-out (R30):** users who cannot tolerate the widened attack surface can set `CORTEX_AUTO_INSTALL=0` in their environment. Both Layer 2 and Layer 3 silent-skip on this environment variable; users then perform manual `uv tool install --reinstall --refresh-package cortex-command git+...@<tag>` updates on their own cadence. This is the supported escape hatch for security-conscious users who want Layer 1 marketplace updates but not auto-reinstall.
- **Future work (explicitly deferred):** stronger mitigations — **Sigstore/cosign signing** of release artifacts so the install path verifies a cryptographic signature before executing the new wheel, and **TOFU (trust-on-first-use) SHA recording** so the first observed SHA for a given tag becomes the trust anchor and force-pushes are detected as SHA mismatches — are out of scope for this ticket. They are noted as the future-work direction once the operator-controlled ruleset proves insufficient.

### Chicken-and-egg paradox of in-CLI_PIN SHA pinning

The obvious in-code mitigation — extending `CLI_PIN` from a `(tag, schema)` 2-tuple to a `(tag, schema, sha)` 3-tuple so the install path could verify the resolved tag's SHA against the embedded SHA — is unimplementable as written. The release commit's tree cannot contain its own SHA: the rewrite step that writes the new `CLI_PIN` into `cli_pin.py` produces a tree whose hash depends on the bytes of `cli_pin.py`, and those bytes would need to contain the hash of the tree they are about to be part of. Two-pass workarounds (rewrite, commit, then move the tag to the second commit that includes the first commit's SHA) break the round-trip — installing via SHA pulls the *first* commit's tree, which has a stale or placeholder SHA. The chicken-and-egg paradox rules out the in-CLI_PIN approach entirely; this is why the immediate mitigation is the GitHub Ruleset (a force-push prevention, not a force-push detection), and the future-work direction is signing/TOFU (which break the SHA-of-self circularity by anchoring trust outside the release tree).

### Release prerequisite (pre-merge operator action)

**Before merging this lifecycle's PR**, the operator MUST verify on `https://github.com/charleshall888/cortex-command/settings/rules` that a Repository Ruleset exists with tag-pattern `v*` and the `Restrict updates` and `Block force pushes` rules enabled. The operator MUST attach to the PR description either a screenshot of the configured ruleset page or the output of a `gh api` query (e.g., `gh api repos/charleshall888/cortex-command/rulesets`) demonstrating that the ruleset is in effect. **Without the screenshot or `gh api` output attached to the PR description, the PR is not mergeable.** This makes the operator action a hard release gate, not an advisory note — the codebase cannot enforce the ruleset's existence, so the PR description becomes the load-bearing artifact.

---

## Release ritual

The post-fix happy-path release ritual is:

1. **Write code → push to main.** Normal commit flow; no manual version bump.
2. **`auto-release.yml` runs on push to main.** The workflow invokes `bin/cortex-auto-bump-version` to compute the next semver tag, runs `bin/cortex-rewrite-cli-pin` to rewrite `CLI_PIN[0]` in `plugins/cortex-overnight/server.py`, commits the rewrite with subject `Release vX.Y.Z`, tags `vX.Y.Z` at that commit, and pushes both the branch and the tag using a Personal Access Token (PAT). The PAT is required because `GITHUB_TOKEN`-authored pushes do not retrigger workflows; the PAT-authored tag push retriggers `release.yml`. The workflow self-skips on retrigger via a subject-prefix filter (`startsWith('Release v')`); belt-and-suspenders, the bumper itself returns `no-bump` because the new tag points at the release commit (empty `<tag>..HEAD` range).
3. **`release.yml` fires on the new tag.** The first job is `cli-pin-lint` — defense-in-depth that asserts `CLI_PIN[0]` matches the pushed tag and hard-fails the release if not. The second job builds the wheel via `uv build --wheel` and publishes a GitHub Release with `dist/*.whl` attached.
4. **Wheel is published.** The marketplace fast-forward path (Layer 1) carries the plugin update to user machines; the next MCP tool call (Layer 2) triggers the CLI reinstall via `uv tool install --reinstall`.

The CI lint at `release.yml` is **defense-in-depth for manual emergencies** (PAT revoked, workflow disabled, manual tag push from a branch where `CLI_PIN[0]` was not bumped). On the happy path, `auto-release.yml` already bumped `CLI_PIN[0]` before tagging, so the lint is redundant but cheap; it ensures a stale wheel is never published even when the auto-release path is bypassed.

### PAT authentication scheme (maintainer-only)

The PAT push in step 2 uses **HTTP Basic** with username `x-access-token` and the PAT as the password, base64-encoded — matching `actions/checkout@v4`'s production scheme. This is not interchangeable with the `Bearer` scheme GitHub's REST API accepts: GitHub's git smart-HTTP backend advertises `WWW-Authenticate: Basic realm="GitHub"` on every 401 and rejects all non-Basic schemes. Empirical results from `.github/workflows/pat-auth-scheme-probe.yml`:

| Scheme | HTTP code | WWW-Authenticate returned |
|---|---|---|
| `Authorization: Bearer <PAT>` (capital B) | 401 | `Basic realm="GitHub"` |
| `Authorization: bearer <PAT>` (lowercase) | 401 | `Basic realm="GitHub"` |
| `Authorization: token <PAT>` (legacy GitHub) | 401 | `Basic realm="GitHub"` |
| `Authorization: Basic base64(x-access-token:<PAT>)` | **200** | — (authenticated) |
| (no Authorization header — anonymous) | 401 | `Basic realm="GitHub"` |

The scheme rejection happens at the auth-middleware layer, before token-permission checking. Adding additional PAT permissions does not unblock non-Basic schemes. To re-verify if GitHub changes their server contract, dispatch the diagnostic workflow via `gh workflow run pat-auth-scheme-probe.yml`.

---

## Intent vs currently-wired

The audit table below names the load-bearing components, their intended behavior, and the currently-wired behavior after this feature lands. Discrepancies (if any) are explicit, not implied by absence.

| Component | Intended behavior | Currently-wired behavior |
|---|---|---|
| `CLI_PIN[0]` propagation | Every release tag updates `CLI_PIN[0]` to the new tag so the plugin and CLI stay paired across `vX.Y.Z` boundaries. | `auto-release.yml` runs `bin/cortex-rewrite-cli-pin` on push to main, commits the rewrite, and tags via PAT so `release.yml` fires; the CI lint blocks the release on drift as defense-in-depth. |
| `CLI_PIN[1]` schema floor | Bumps in lockstep with the CLI's `_JSON_SCHEMA_VERSION` so the plugin rejects schema-incompatible CLIs. | `CLI_PIN` and `MCP_REQUIRED_CLI_VERSION` both pin to `"2.0"`; the schema-floor check at `_schema_floor_violated` rejects mismatched majors with a stderr remediation message. |
| `cortex --print-root` envelope | Carries package version in `version` and schema floor in `schema_version` so MCP consumers can compare on independent cadences. | `cortex_command/cli.py:232` emits both fields per the v2.0 envelope migration documented in [`mcp-contract.md`](mcp-contract.md); the package version is sourced from `importlib.metadata.version("cortex-command")`. |
| `_ensure_cortex_installed` reinstall branch | On version mismatch, acquires a flock and runs `uv tool install --reinstall git+<url>@CLI_PIN[0]` synchronously before delegating to the CLI. | `_ensure_cortex_installed` at `server.py:775` runs the version comparison via `packaging.version.Version`, consults the vendored install guard, and emits per-stage NDJSON audit records (`version_mismatch_reinstall`, `version_mismatch_reinstall_parse_failure`, `version_mismatch_blocked_by_inflight_session`). |
| In-flight install guard | Stdlib-only core that blocks reinstall when an overnight session is active, byte-identical between CLI and plugin sources. | `cortex_command/install_guard.py:check_in_flight_install_core` is mirrored verbatim to `plugins/cortex-overnight/install_guard.py:check_in_flight_install_core`; `.githooks/pre-commit` enforces byte-level parity, and `tests/test_install_guard_parity.py` asserts identical decisions across the carve-out matrix. |
| `_schema_floor_violated` stderr surface | On schema-floor mismatch under wheel install, emits a single-line stderr remediation message naming the installed schema, required schema, and reinstall command. | `_schema_floor_violated` at `server.py:1827` emits `Schema-floor violation: installed CLI schema_version=X.Y, required={CLI_PIN[1]}; run 'uv tool install --reinstall git+...@{CLI_PIN[0]}' to upgrade` before returning. |
| CI lint (defense-in-depth) | Hard-fails the release job when `CLI_PIN[0]` does not match the pushed tag so a stale wheel is never published. | `release.yml:28` runs `cli-pin-lint` as a `needs:` prerequisite for the `release` job; the lint exits non-zero on drift and blocks the wheel publish. |
| Bash-tool subprocess carve-out | Direct shell-out to `cortex …` bypasses Layer 2 by design; the gap is a documented wontfix, not coverage. | Documented in [Bash-tool subprocess carve-out](#bash-tool-subprocess-carve-out) above; the `implement.md §1a` preflight surfaces the gap loudly as a fail-fast diagnostic. |

---

## Residual risks

The flow above closes the three structural gaps that motivated this ticket. The following risks remain explicitly out of scope:

- **Marketplace fast-forward (Layer 1).** Anthropic owns the force-pushed-tag, session-restart-timing, and tag-not-yet-on-origin paths. The real-install test (R23) covers cortex-command-side mismatch detection only.
- **Pre-v2.0.0 plugin paired with v2.0.0+ CLI.** Hard-fail by design; the old plugin's `_parse_major_minor` reads the new envelope's `version` field as a PEP 440 string and raises `ValueError`. One-time coordinated reinstall of both halves is required; the marketplace fast-forward (Layer 1) recovers within one session-restart cycle.

Force-pushed-release-tag stale-wheel risk is now closed by `_run_install_and_verify`: the install argv carries `--refresh-package cortex-command` between `--reinstall` and the git URL (#235), so a force-pushed release tag invalidates the uv git cache entry for `cortex-command` without touching transitive PyPI caches. The same flag appears in every user-facing remediation string so the manual recovery path matches the auto-recovery argv.

---

## Related

- [`docs/setup.md#upgrade--maintenance`](../setup.md#upgrade--maintenance) — user-facing upgrade summary.
- [`docs/internals/mcp-contract.md`](mcp-contract.md) — subprocess + JSON contract between the MCP plugin and the CLI; schema versioning rules; forever-public-API guarantees.
- [`.github/workflows/auto-release.yml`](../../.github/workflows/auto-release.yml) — auto-bump + tag-push workflow.
- [`.github/workflows/release.yml`](../../.github/workflows/release.yml) — tag-triggered wheel build + GitHub Release; carries the CI lint.
- `bin/cortex-auto-bump-version`, `bin/cortex-rewrite-cli-pin` — release-ritual helpers invoked by `auto-release.yml`.
- `tests/test_mcp_auto_update_real_install.py` — end-to-end real-install integration test covering every enumerated branch of `_ensure_cortex_installed`.
- `tests/test_install_guard_parity.py` — byte-identity parity test for the vendored install guard.
