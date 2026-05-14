[← Back to Agentic Layer](../agentic-layer.md)

# Auto-update Architecture

**Internal reference — not a user-facing skill.** For the user-facing summary, see [`docs/setup.md#upgrade--maintenance`](../setup.md#upgrade--maintenance).

This doc is the authoritative source-of-truth for how the cortex-overnight plugin and the cortex CLI stay version-coupled. It synthesizes the two-layer architecture (Claude Code marketplace clone + MCP-tool-call-gated CLI reinstall), the load-bearing component map, the release ritual end-to-end, and an Intent vs currently-wired audit. Sibling docs in this directory ([`mcp-contract.md`](mcp-contract.md), [`pipeline.md`](pipeline.md), [`sdk.md`](sdk.md)) cover adjacent contracts and module internals; this doc owns the auto-update flow itself.

---

## Intent

Cortex-command ships as two halves that must stay paired in version: the `cortex-overnight` plugin (refreshed by Claude Code's marketplace mechanism) and the `cortex` CLI (installed via `uv tool install` and refreshed by `uv tool install --reinstall`). The user-visible promise is that turning on "Auto-Update Marketplace Plugins" in Claude Code is the only manual step a user takes — the plugin and the CLI stay in lockstep without further intervention. A new release shipped to the upstream repository propagates to the user's machine within one Claude Code session-restart plus one MCP tool call.

The architecture is structured so the user never has to reason about which half is stale. The plugin carries an embedded `CLI_PIN` constant naming the CLI tag it expects; the next MCP tool call after a plugin refresh observes the mismatch between the installed CLI version and `CLI_PIN[0]` and runs `uv tool install --reinstall` synchronously before delegating to the CLI. The schema-floor check at `_schema_floor_violated` (see [Component map](#component-map)) hard-rejects any payload whose major schema-version differs from the plugin's baked-in floor, so a paired-but-incompatible plugin/CLI combination surfaces as an actionable remediation message rather than silent miscomputation.

The auto-update flow is deliberately MCP-tool-call-gated: only invocations that route through the plugin's MCP server trigger the reinstall. Bash-tool subprocess dispatches that shell out to `cortex …` directly bypass this layer by design (see the [Bash-tool carve-out](#bash-tool-subprocess-carve-out) below). The `implement.md §1a` preflight surfaces the gap loudly when it bites, treating it as a fail-fast diagnostic rather than coverage that closes it.

---

## Two-layer architecture

Upgrades happen in two layers, and it helps to keep them mentally distinct because Claude Code owns the first layer and cortex-command owns the second.

### Layer 1: marketplace fast-forward at Claude Code startup

When Claude Code launches, the plugin marketplace mechanism refreshes the local clone of the plugin repository (including the `cortex-overnight` server module that carries the `CLI_PIN` constant). This is the layer where a `CLI_PIN` bump arrives on the user's machine. Claude Code controls this layer end-to-end; cortex-command does not. The marketplace's fast-forward semantics — force-pushed-tag handling, session-restart timing, tag-not-yet-on-origin race — are Anthropic-owned and treated as residual risk from this doc's perspective.

A user who disables marketplace auto-updates pins the embedded `CLI_PIN` to whatever tag was current at plugin install time. Schema versions still match between the embedded `CLI_PIN[1]` and the installed CLI's print-root envelope, so a stale-but-self-consistent plugin/CLI pair keeps working — the user just stays at the older version until they manually refresh the plugin.

### Layer 2: MCP-tool-call-gated CLI reinstall

The next time the `cortex-overnight` MCP server is invoked (e.g., `overnight_start_run`, `overnight_status`), the entry-point helper `_resolve_cortex_argv` calls `_ensure_cortex_installed` (see [Component map](#component-map)) before delegating to the CLI. That function runs the first-install check and the version-comparison reinstall check; on mismatch, it acquires a flock, runs `uv tool install --reinstall git+<url>@CLI_PIN[0]`, and verifies the install via the absolute-path-pinned `cortex --print-root --format json` probe. The MCP server owns this layer end-to-end and does not import the cortex Python package — its sole interface to the CLI is the subprocess + JSON contract documented in [`mcp-contract.md`](mcp-contract.md).

The reinstall fires only under `uv tool install`-style wheel installs. Editable installs from a `cortex/` development clone short-circuit the reinstall branch via skip predicates (`CORTEX_DEV_MODE=1`, dirty working tree, non-`main` branch), since the dogfooding case wants `pip install -e .` semantics and the user manages CLI versions directly.

### Bash-tool subprocess carve-out

Bash-tool subprocess dispatches that shell out to `cortex …` directly — without going through the MCP server — do **not** trigger Layer 2. This is an intentional gap (see `#145`'s wontfix), not an oversight: routing every CLI subprocess through the MCP server would require either Claude Code-side instrumentation or a CLI-side phone-home, both of which violate the plugin-imports-zero-cortex-modules contract. The `implement.md §1a` preflight is a fail-fast diagnostic that surfaces the gap loudly when it bites.

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

---

## Release ritual

The post-fix happy-path release ritual is:

1. **Write code → push to main.** Normal commit flow; no manual version bump.
2. **`auto-release.yml` runs on push to main.** The workflow invokes `bin/cortex-auto-bump-version` to compute the next semver tag, runs `bin/cortex-rewrite-cli-pin` to rewrite `CLI_PIN[0]` in `plugins/cortex-overnight/server.py`, commits the rewrite with `[release-type: skip]` in the body, tags `vX.Y.Z`, and pushes both the branch and the tag using a Personal Access Token (PAT). The PAT is required because `GITHUB_TOKEN`-authored pushes do not retrigger workflows; the PAT-authored tag push retriggers `release.yml`.
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
- **Force-pushed release tag.** `uv tool install --reinstall` may serve a stale wheel from the uv cache when a release tag is force-pushed. Recommended remediation: `uv cache clean cortex-command` before reinstall on suspected force-push.
- **Pre-v2.0.0 plugin paired with v2.0.0+ CLI.** Hard-fail by design; the old plugin's `_parse_major_minor` reads the new envelope's `version` field as a PEP 440 string and raises `ValueError`. One-time coordinated reinstall of both halves is required; the marketplace fast-forward (Layer 1) recovers within one session-restart cycle.

---

## Related

- [`docs/setup.md#upgrade--maintenance`](../setup.md#upgrade--maintenance) — user-facing upgrade summary.
- [`docs/internals/mcp-contract.md`](mcp-contract.md) — subprocess + JSON contract between the MCP plugin and the CLI; schema versioning rules; forever-public-API guarantees.
- [`.github/workflows/auto-release.yml`](../../.github/workflows/auto-release.yml) — auto-bump + tag-push workflow.
- [`.github/workflows/release.yml`](../../.github/workflows/release.yml) — tag-triggered wheel build + GitHub Release; carries the CI lint.
- `bin/cortex-auto-bump-version`, `bin/cortex-rewrite-cli-pin` — release-ritual helpers invoked by `auto-release.yml`.
- `tests/test_mcp_auto_update_real_install.py` — end-to-end real-install integration test covering every enumerated branch of `_ensure_cortex_installed`.
- `tests/test_install_guard_parity.py` — byte-identity parity test for the vendored install guard.
