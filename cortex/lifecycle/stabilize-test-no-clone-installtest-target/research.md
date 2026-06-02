# Research: Stabilize `test_no_clone_install::test_target_state` against uv-cache-lock timeout flake

**Scope anchor (from Clarify):** Make `test_target_state` — and the small CLASS of *default-run* tests that genuinely contend on the real `~/.cache/uv/.lock` — deterministic by isolating the uv cache per-test via `UV_CACHE_DIR=<tmpdir>` (the established repo precedent), without weakening the install-regression assertions the gate exists to catch. Scope decision already made: cover the class, not just the one observed-failing test.

**Bottom line:** The diagnosis is correct in mechanism (shared-cache-lock contention) but wrong in two of its three named contenders. The fix is `UV_CACHE_DIR` per-test isolation — load-bearing, precedent-backed, and immune to *every* external uv contender regardless of which one actually fired. The genuine default-run set is **2 tests, not ~17**. `@pytest.mark.serial` is inert today (no xdist installed) and at most documentary.

---

## Codebase Analysis

### A. Genuine real-lock default-run set — **2 tests, not ~17**

The ticket's "~17 uv-invoking tests" counts files that *textually reference* uv. The genuine set that (1) is NOT `@pytest.mark.slow` (so it runs in default `just test`) AND (2) actually shells out to **real** `uv` touching the shared `~/.cache/uv/.lock` is **two**:

| Test file | Function | Real-uv call | Has `UV_CACHE_DIR`? | Has `@serial`? |
|---|---|---|---|---|
| `tests/test_no_clone_install.py` | `test_target_state` (+ `built_wheel` module fixture) | `uv build --wheel` (fixture L72) + `uv tool install --reinstall` (`_install_wheel_isolated` L133) | **No → NEEDS ISOLATION** | No |
| `tests/test_mcp_subprocess_contract.py` | `test_plugin_path_mismatch_exits_nonzero` (L87) | `uv run --script <server.py>` (L105) — PEP 723 dep-resolution touches the shared cache | **No → NEEDS ISOLATION** | No |

Everything else classifies out: `test_mcp_auto_update_real_install.py` (all 6) is `@slow`+`@serial` and **already** isolates `UV_CACHE_DIR` (L165/206/408); the other "uv" matches are MOCKED (`test_cli_upgrade.py`, `test_mcp_cortex_cli_missing.py`, `test_no_clone_install.py::test_mcp_first_install_hook`), PATH-STUBBED hermetic (`test_install.sh`, `test_cli_background_install_hook.py` via `tests/fixtures/install/bin/uv`), or console-shim/`python -m` (no uv cache contact).

**Known latent gaps (OUT of this ticket's default-run scope, note-only):** `test_mcp_auto_update_orchestration.py::test_verification_probe_fails_on_corrupt_install` (L1133, `@slow`, not isolated) and `test_release_artifact_invariants.py::test_wheel_package_version_matches_git_describe` (L197, `@slow`, not isolated). They share the failure mode but are opt-in, so they don't flake the default suite. Worth a one-line spec note, not a blocker.

### B. Precedent mechanics (`tests/test_mcp_auto_update_real_install.py`)

Per-test cache isolation is threaded into the **subprocess `env` dict** — no shared fixture, no process-env monkeypatch:

```python
cache_dir = tmp_path / "uv_cache_a"          # distinct dir under pytest tmp_path
cache_dir.mkdir(parents=True, exist_ok=True) # before install (build tolerates absent dir)
env = os.environ.copy()
env["UV_CACHE_DIR"] = str(cache_dir)          # L165 (build) / L206 (install) / L408 (inline)
subprocess.run(["uv", "build", "--wheel", ...], env=env, timeout=300)
subprocess.run(["uv", "tool", "install", "--reinstall", str(wheel)], env=env, timeout=300)
```
Every such test pairs `@pytest.mark.slow` + `@pytest.mark.serial`. The cache dir lives under `tmp_path`; isolation (not the 300s timeout) is what removes contention.

### C. Target test mechanics (`tests/test_no_clone_install.py`)

- **`built_wheel` MODULE-scoped fixture (L58-106):** runs `uv build --wheel` with **NO `env=` passed** (L71-77) → inherits process env → **uses the shared `~/.cache/uv/`**. Timeout **180s**.
- **Egress-block skip (L78-93):** fires only when `returncode != 0` AND output contains `"Tokio executor failed"`/`"system-configuration"` (uv's immediate panic signature). **It does NOT catch `TimeoutExpired`** — that exception is raised by `subprocess.run(..., timeout=180)` before `returncode` is inspected, so it escapes both the skip and the `pytest.fail` branch and surfaces as a raw error. Confirmed: this is exactly the flake.
- **`_install_wheel_isolated` (L114-145):** builds `env = os.environ.copy()` and sets `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`, `PATH` — **but NOT `UV_CACHE_DIR`** (L127-130). This is the isolation gap. Timeout **180s**.
- **Probes** (`cortex --print-root` 30s; `python -c` importlib.resources 15s ×N over `PACKAGE_INTERNAL_SITES`) do **not** invoke uv → no cache contact. Only build + install touch the lock.

**Exact insertion points:** (1) `built_wheel` fixture — add a `tmp_path_factory`-rooted cache dir, build `env` with `UV_CACHE_DIR`, pass `env=env` to the `uv build` call. (2) `_install_wheel_isolated` — add `cache_dir = tmp_path / "uv_cache"; cache_dir.mkdir(...)` and `env["UV_CACHE_DIR"] = str(cache_dir)` beside the existing tool/bin assignments. (3) `test_mcp_subprocess_contract.py` — add the `UV_CACHE_DIR` key to the existing `env` dict at L110-115.

### D. justfile + markers + xdist

- **`just test`** runs sub-suites + hermetic `bash tests/test_install.sh` + `.venv/bin/pytest tests/ -q` — **no `--run-slow`** (so `@slow` never runs). `@slow` gating is implemented in `tests/conftest.py::pytest_collection_modifyitems` (L14-20), not addopts.
- **`pyproject.toml` markers (L94-98):** `slow`, `serial`, `structural_equivalence` registered with descriptions. No `--strict-markers`. Convention: every marker carries a description.
- **xdist: NOT installed, NOT configured** (dev deps are only `pytest>=8.0`, `pytest-repeat>=0.9.3`). pytest runs single-process → **`@pytest.mark.serial` is currently inert** (nothing parallelizes). It would only bind if a parallel runner with marker grouping is later introduced.

**Files that will change:** `tests/test_no_clone_install.py`, `tests/test_mcp_subprocess_contract.py` (and optionally the `pyproject.toml` marker list if `serial` is added). None are under lifecycle-gated paths (`skills/`, `hooks/`, `bin/cortex-*`, …).

---

## Web Research

**1. uv cache lock — HIGH confidence.** The global lock is `$UV_CACHE_DIR/.lock` (default `~/.cache/uv/.lock`), scoped to the **whole cache directory**. Concurrent uv processes doing cache-*modifying* work (build / `tool install` / `cache` ops) **serialize** on it; uv's verbose output literally prints `Waiting to acquire lock for … at .cache/uv/.lock` (astral-sh/uv#16112). The wait timeout is `UV_LOCK_TIMEOUT`, **default 300s** (uv env-vars docs). **This is the smoking gun:** uv blocks waiting on the lock up to 300s, but the test's **180s subprocess timeout fires first** → `TimeoutExpired`. It does not block indefinitely; it errors after `UV_LOCK_TIMEOUT`.

**2. `UV_CACHE_DIR` isolation — HIGH confidence.** Because the lock lives *inside* the cache dir, a unique per-test tmpdir gives each process its **own cache and its own lock**, fully removing cross-process contention — the same mitigation uv users apply to concurrent CI jobs (astral-sh/uv#10286). No first-class "shared read-only base + isolated lock" mode exists; per-test isolated cache is the simplest contention-free choice.

**3. Cold-cache cost — MEDIUM-HIGH confidence.** For a **small pure-Python wheel with no/minimal deps**, a cold `UV_CACHE_DIR` stays **well under 180s** — seconds, not minutes. Cold cost is dominated by registry *download*, not local build; a local-wheel build/install with minimal deps downloads little. Warm installs are sub-second (hardlinks). No published cold timing for this exact `uv build`+`uv tool install` of a trivial wheel → **recommend a one-time local measurement** to lock the number.

**4. pytest serialization — HIGH confidence.** `serial`/serialization is **meaningless without xdist** — plain pytest already runs sequentially in one process. Standard guidance for a shared *external* resource: **prefer isolating the resource (separate cache dir) over serializing access** — isolation removes contention entirely and preserves future parallelism.

**5. Anti-pattern check — HIGH confidence.** Lengthening a timeout or adding blind retries on a correctness-gate test is the recognized anti-pattern (masks failures, accrues reliability debt). Endorsed fix is determinism via isolation. Directly validates `UV_CACHE_DIR` isolation over timeout-bumping/retry.

Sources: uv [Caching](https://docs.astral.sh/uv/concepts/cache/), [Environment variables](https://docs.astral.sh/uv/reference/environment/) (`UV_LOCK_TIMEOUT` default 300s; `UV_CACHE_DIR`), [BENCHMARKS.md](https://github.com/astral-sh/uv/blob/main/BENCHMARKS.md); astral-sh/uv [#16112](https://github.com/astral-sh/uv/issues/16112), [#10286](https://github.com/astral-sh/uv/issues/10286); pytest-xdist how-to; flaky-test anti-pattern write-ups (Harness, Semaphore, TestRail). All fetches succeeded.

---

## Requirements & Constraints

- **`project.md` Quality bar (L23):** "Tests pass; … ROI matters — ship faster, not be a project." Anchors a proportionate fix (no test-infra overhaul). **Complexity/Solution-horizon (L19/L21):** "simpler wins"; per-test isolation is the established narrow fix, not a speculative redesign. No formal "determinism" quality attribute exists; the closest hooks are per-feature spec R-numbers and the `serial` convention. No requirement codifies a CI/Complete-gate dependency on `just test` determinism, though Complete *does* run tests (ADR-0004) so flakiness surfaces there in practice.
- **Pre-commit gates on `tests/*` — WILL fire, should pass cleanly.** `.githooks/pre-commit` runs Phase 1.5 `just check-parity --staged` (L81) and the contract gate `just check-contract --staged` (L106) on staged `tests/*`. For an edit limited to test files + the `pyproject.toml` marker list, no SKILL/CLI surface is touched, so both pass. Other phases (backlog telemetry, events-registry, prescriptive-prose, bare-python L201, install-guard/cli-pin) do **not** include `tests/*` in their trigger globs. Keep `pyproject.toml` valid TOML.
- **`serial` / R26 / Task 20 rationale.** `pyproject.toml:96` is the canonical description ("tests that spawn real subprocesses and must not run in parallel against each other (R26 / Task 20)"). R26 is a per-lifecycle spec requirement (origin: archived `rebuild-overnight-runner-under-cortex-cli/spec.md`), not a global constant; rationale lives in the pyproject description + per-test docstrings. The marker is **advisory/documentary today** (no xdist).
- **No-masking is the governing HOW-constraint, enforced by precedent not a standalone requirement.** `test_target_state`'s docstring (L5-13, 193-205) states it "is the gate that catches `Path(__file__)` regressions that silently break under a non-editable install," probing six `importlib.resources` sites. The `@slow` sibling deliberately routes the egress panic to `pytest.fail(...)` rather than skip (L48-55) "so an overnight runner … reports the gap explicitly rather than silently passing." The fix must preserve all install-regression probes intact — `UV_CACHE_DIR` isolation addresses contention without touching them.
- **Marker documentation convention** is the only registration requirement: reusing `serial` needs nothing new; adding a *new* marker would need a `pyproject.toml` description line. No ADR covers hermetic tests / uv-tooling test surface.

---

## Trigger & External-Contender Forensics

**Q1 — contention vs genuine slowness → contention strongly favored.** The two 180s budgets sit on `uv build` (fixture L71-77) and `uv tool install` (L132-138); the 30s/15s probes are too small to be the ~175s blocker. In isolation the whole test is ~5.5s, so a 180s timeout means one `uv` call blocked ~175s beyond its warm baseline. A local-wheel build/install (no git clone, no large download) makes a 30× cold-rebuild blow-up implausible; a lock-wait that parks on the shared cache lock until the subprocess budget expires fits exactly. **"Green on immediate re-run, ~5.5s in isolation" is the signature of a transient external lock-holder, not a persistent slowness regression.** Corroborated by uv's 300s `UV_LOCK_TIMEOUT` > the test's 180s subprocess timeout (Web §1).

**Q4 — external uv contenders.** Three layers can fire a slow, cache-lock-holding `uv tool install --reinstall git+…` (`docs/internals/auto-update.md`):
- **Layer 2 — MCP auto-update** (`plugins/cortex-overnight/server.py:425-640`): fires on every cortex subprocess from MCP tool handlers; gated by `CORTEX_AUTO_INSTALL=0`; the version-mismatch git-reinstall branch (L512-623) consults the in-flight session guard (L597-617) and is **blocked during a healthy active overnight session** unless `CORTEX_ALLOW_INSTALL_DURING_RUN=1`.
- **Layer 3 — SessionStart async hook** (`hooks/cortex-cli-background-install.sh` → `install_core.run_install_in_background`, `plugins/cortex-overnight/install_core.py:932,1208-1216): the **most plausible mid-`just test` contender** — fires on every Claude Code SessionStart (the overnight runner spawns sessions throughout a run), spawning a detached `uv tool install --reinstall … git+…` on the **shared** cache (no `UV_CACHE_DIR`). Skip predicates include `CORTEX_DEV_MODE=1`, `CORTEX_AUTO_INSTALL=0`, dirty tree, non-main branch, and the same in-flight session guard (L1076-1094).
- **Layer 1** (marketplace `CLI_PIN` fast-forward) is not a uv-firing path.

The guards make Layer 2/3 *less* likely during a healthy run, but they're not airtight at the **Complete gate** specifically (the session is transitioning toward complete; a fresh interactive SessionStart could fire while the guard reads stale/complete state), and **any** other machine-local uv (concurrent agent `uv install -e .` per the worktree-editable-pth memory, a second Claude session, the dashboard) contends on the same shared lock. So the auto-update hook is *plausible-but-not-proven* as the specific trigger; the shared-cache-lock framing is the robust one.

**Isolation-immunity verdict → YES; separate hook-gating NOT needed.** uv's lock is per-cache-directory. Pointing `UV_CACHE_DIR` at a tmpdir-private cache makes the test's `uv` acquire a lock on *that* private cache, which **no external uv can ever contend on** — Layer 2, Layer 3, concurrent agent installs, anything. Hook-gating-during-tests would be fragile (only covers cortex's own two hooks, needs a test-detection signal threaded in) and strictly less complete than isolation. **Choose isolation.**

**Single-observation caveat.** Proven: the test shares the global cache (no `UV_CACHE_DIR`); both governing calls have 180s budgets; three code paths can fire a slow cache-lock-holding install; the `@slow` sibling already isolates its cache (fix pattern is established here). Hypothesized (one failure, 1729 passed, green on retry): that a concurrent uv actually held the lock during #279, and specifically which one. **The fix is correct independent of trigger confirmation** — removing the shared resource neutralizes every plausible contender at once; confirmation would only matter if one *also* wanted to harden the hooks, which isolation makes redundant for de-flaking this test.

---

## Tradeoffs & Alternatives (three ticket options assessed)

- **Option A — per-test `UV_CACHE_DIR` isolation (RECOMMENDED).** Removes the shared lock entirely; immune to all external contenders; matches established repo precedent; preserves every assertion. Cost: cold cache per test (seconds for a small wheel, well under 180s — verify locally). Strictly preferred.
- **Option B — bounded retry / longer timeout.** Rejected: masks the contention and weakens a correctness gate (anti-pattern, Web §5); violates the no-masking HOW-constraint; doesn't fix root cause.
- **Option C — quarantine/serialize via `@pytest.mark.serial`.** Inert today (no xdist) so it changes nothing in `just test`; even with xdist it only orders the *in-suite* tests and does **nothing** against an out-of-process background uv install — which is the actual trigger. At most a documentary add-on to A, not a substitute.

**Recommendation:** Option A. Optionally add `@pytest.mark.serial` to the two targets as forward-compat documentation consistent with the precedent, but spec should state explicitly that `UV_CACHE_DIR` is the load-bearing mechanism and `serial` is documentary/inert today.

---

## Open Questions

- **Cold-cache timing (deferred → verify in Implement, not a blocker):** Web research puts a cold `UV_CACHE_DIR` build+install of a small pure-Python wheel at seconds, comfortably under 180s, but found no published number for this exact operation. Resolution: after adding isolation, run `test_target_state` (and the second target) and confirm wall-clock stays well under the 180s budgets so isolation doesn't introduce a *new* timeout failure mode. Low risk.
- **Add `@pytest.mark.serial` or not (deferred → Spec decision):** It is inert today (no xdist) and does not address the out-of-process trigger. Spec should decide between (a) `UV_CACHE_DIR` only (minimal, YAGNI per Complexity philosophy) or (b) `UV_CACHE_DIR` + documentary `serial` for precedent-consistency. Either is defensible; the load-bearing fix is identical.
- **`@slow` latent-gap tests (resolved by the scope decision — note-only):** `test_mcp_auto_update_orchestration.py::test_verification_probe_fails_on_corrupt_install` and `test_release_artifact_invariants.py::test_wheel_package_version_matches_git_describe` share the failure mode but are opt-in (`@slow`), so they're outside the "default-run class" scope already chosen. Surface as a known latent gap in the spec; do not fix here.
