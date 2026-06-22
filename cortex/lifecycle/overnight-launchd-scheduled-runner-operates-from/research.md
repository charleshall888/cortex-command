# Research: Fix scheduled (launchd-fired) overnight runs resolving project root to '/' instead of the correct repo root; and fix `cortex overnight status` crashing on a naive-vs-aware datetime comparison

**Feature:** `overnight-launchd-scheduled-runner-operates-from` · backlog #311 · tier=complex · criticality=high

This ticket bundles two bugs in the overnight runner. Research confirmed the ticket's symptoms, **refined** its stated mechanism (the ticket's "derives root from CWD/env" framing is imprecise), and surfaced **two additional findings the ticket did not name**: (a) the persistent guardian (#308 supervision) is silently broken under launchd by the *same* defect, and (b) the obvious Bug-2 fix (assume-UTC) is a correctness regression.

---

## Codebase Analysis (Bug 1 — root resolution)

**Single R20 resolution site:** `cortex_command/overnight/cli_handler.py:141-156` — `_resolve_repo_path()` runs `git rev-parse --show-toplevel`, then falls back to `Path.cwd()`. It does **not** read `CORTEX_REPO_ROOT`. Under launchd (CWD=`/`), `git rev-parse` fails (not a repo) → returns `Path("/")`.

**The heart of the bug:** `overnight-state.json` stores a **correct** `project_root` (field `state.py:260`; written from `repo_root` at session create, `plan.py:412/524/560/567/714`), reachable via the always-absolute `--state`. But the start/execution path **never reads `state.project_root`** to set the working root — `repo_path` is computed independently from `_resolve_repo_path()` (`handle_start:616`) and threaded as `project_root=repo_path` into `runner.run`.

**Env poisoning:** `runner.py:2503` sets `os.environ["CORTEX_REPO_ROOT"] = str(repo_path)`. When `repo_path=/`, this poisons the env for **all** children — so even the env-first deeper resolvers (`common._resolve_user_project_root` used by `feature_executor`/`orchestrator`/`batch_runner`) return `/`. This explains 0/4 features, `fatal: not a git repository`, and `project_root: "/"`.

**Two correct-but-unused signals already exist:**
- The per-session plist `_snapshot_env` (`macos.py:639-658`, `_OPTIONAL_ENV_KEYS` :59-64) captures `CORTEX_REPO_ROOT` into the launchd job's `EnvironmentVariables` **only if it was already set in the scheduling shell** at `cortex overnight schedule` time (usually absent). The **guardian** plist (`macos.py:1173-1176`) sets it **unconditionally** — a telling asymmetry.
- `launcher.sh` receives `repo_root` as plist `ProgramArguments[1]` (`macos.py:617-621`) but **ignores it** (it uses `@@`-substituted markers, not `$1`); it invokes `cortex overnight start --state <abs> --format json --force --scheduled` — no root argument.

**Per-feature `repo: null`:** resolves to "home repo" = `Path.cwd()` (`feature_executor.py:685`, `runner.py:729-731`), which is `/` under launchd. The ticket's "treat `repo: null` as the session's `project_root`" is correct; anchoring on `state.project_root` fixes it.

**R20 boundary:** the single resolution site is `_resolve_repo_path`; everything downstream (`runner.run`, `_spawn_runner_async`, `_start_session` pid/pointer writes, the `runner.py:2503` env export) is **propagation, not resolution**. The fix must stay at the one site.

**Files that will change:** `cortex_command/overnight/cli_handler.py` (primary).

## Codebase Analysis (Bug 2 — status tz crash)

**Root cause:** `status.py:_now()` (`:94-95`) returns UTC-aware (`datetime.now(timezone.utc)`); `status.py:_parse_iso()` (`:98-100`) is a bare `datetime.fromisoformat(ts)` with **no tz normalization** — naive when the string has no offset, aware when it carries `+00:00`. Comparing the two raises `TypeError: can't compare offset-naive and offset-aware datetimes`, caught at `cli_handler.py:900` and printed as `Error reading status: ...`.

**The live crash (in the reported *scheduled* session):** `_is_scheduled_dormant` (`status.py:154-181`) does `fires_at = _parse_iso(state.scheduled_start)` then `if fires_at <= now` (`:177`). `scheduled_start` is written **naive LOCAL** — `scheduler/macos.py:parse_target_time` (`:186-260`, docstring "Returns: Naive local datetime", `now = datetime.now()` :213) → `target.isoformat()` (`macos.py:399`, also `cli_handler.py:1744/1784`). Naive-local vs UTC-aware → crash.

**Other vulnerable compare sites** (same `_parse_iso` vs aware `now`): `status.py:336` (`started_at`), `380` (last-event), `405`, `441` (per-feature elapsed). **`started_at` and event `ts` are written tz-aware in production** (`state.py:52` / `events.py:197` via `datetime.now(timezone.utc)`), so `:336` etc. only crash on legacy-naive data; the **operative production crash is `:177` (`scheduled_start`)**.

**In-repo precedent:** `scheduler/macos.py:_is_spent` (`:996-1024`) already normalizes the mismatch — but it attaches **`now.tzinfo`** where its `now = datetime.now()` is **naive/local** (`:860`), i.e. it compares on the value's *local* footing. This precedent supports **attach-local**, not assume-UTC (see Adversarial).

**No shared tz-safe ISO parser exists** in `common.py`; the two repo conventions are (1) writers always emit UTC-aware; (2) readers normalize before compare. The scheduler is the lone writer that emits naive-local.

**Files that will change:** `cortex_command/overnight/status.py` (reader); optionally `scheduler/macos.py` + `cli_handler.py` (writer, durable). Note `_is_spent` reads a *separate* field `ScheduledHandle.scheduled_for_iso` (also naive-local).

## Web Research

- **launchd:** `WorkingDirectory` is the canonical plist key to set a job's CWD (Apple's *Creating Launch Daemons and Agents* explicitly recommends the plist key over in-code `chdir`/`chroot`). Absent it, launchd does not chdir for the job → CWD is `/` (community-documented; Apple docs state the `chdir`-before-job semantics). The environment is **minimal/bare** (no login shell, no `~`/`$VAR` expansion, minimal PATH lacking Homebrew); env must be declared via `EnvironmentVariables`.
- **Daemon root-resolution precedence (recommended):** stored-absolute-path → dedicated env var (in plist `EnvironmentVariables`) → `__file__`-anchor → `git rev-parse` (only when CWD is known inside the repo) → CWD (last resort = the failure here).
- **`git rev-parse --show-toplevel` pitfalls in daemons:** CWD-relative; `safe.directory`/dubious-ownership (CVE-2022-24765) when daemon UID ≠ repo owner; needs `git` on PATH; returns the wrong repo if CWD is inside another tree.
- **Python tz:** `fromisoformat` parses `Z` on 3.11+ (raises on ≤3.10 — pre-substitute `Z`→`+00:00`); returns **naive** when no offset present, in all versions. Canonical idiom: `.replace(tzinfo=utc)` to *attach* UTC to a value known-UTC vs `.astimezone(utc)` to *convert* an aware value — mixing them corrupts times. `datetime.utcnow()` is deprecated; use `datetime.now(timezone.utc)`.

Sources: Apple *Creating Launch Daemons and Agents*; `launchd.plist(5)`; launchd.info; git-rev-parse docs + Atlassian dubious-ownership KB; Python `datetime` docs; bpo-35829; Ruff FURB162; Grinberg "utcnow deprecated".

## Requirements & Constraints

- **R20 (overnight-CLI), exact wording** (`cli_handler.py:3-8`): *"Per R20, the CLI is the single site that resolves user-repo paths (`repo_path`, `session_dir`, `state_path`, `plan_path`, `events_path`) — those paths flow from here as typed parameters into `runner.run`, `ipc`, `logs.read_log`, and `status`."* Counterpart: `runner.py:2393-2395` — *"runner.py itself never derives user-repo paths from `__file__` or env vars (R20)."* **Requires** resolution at exactly one place; **forbids** downstream re-derivation. (Distinct from the *init* R20 in `cortex_command/init/`, which governs `cortex init --update` marker refresh — unrelated.)
- **`status` must stay read-only** (ADR-0011; `observability.md`): *"status is a read-only observability surface; recovery writes must originate from a writer-authorized verb."* The tz fix must **not** repair timestamps on disk.
- **Wheel-vs-working-tree** (`project.md`): the launchd-fired `cortex` binary runs the **installed wheel**, so a working-tree-only fix won't reach scheduled runs until `uv tool install` reinstall. `CORTEX_COMMAND_FORCE_SOURCE=1` forces source for dogfooding.
- **`CORTEX_REPO_ROOT` contract:** `common._resolve_user_project_root()` (`common.py:58-106`) is env-first (trusts the var verbatim, else walks up for `cortex/`); `_resolve_user_project_root_from_cwd()` deliberately ignores it. `_resolve_repo_path()` is **outside** this contract (the gap). R3c (`status.py:84`): forbids module-level capture of `_resolve_user_project_root()` — call at call time.
- **`runner.pid`/`active-session.json` IPC schema** (`pipeline.md`) includes `repo_path` — the launchd `/` propagates here too (ticket evidence). Reads are lock-free by design — a read-only status fix is consistent.
- **Gates a fix must pass:** events registry (`bin/.events-registry.md`) if any new event literal is added (likely none); SKILL-to-bin parity (n/a for Python modules); MUST-escalation policy (prefer soft phrasing). Tests to keep green: `test_common.py` (resolver contract), `test_launcher_*`, `test_scheduler_e2e.py`, `test_spawn_handshake.py`, `test_status*.py`.

## Tradeoffs & Alternatives

Approaches evaluated against R20 and run-now safety:

- **A — `_resolve_repo_path()` consults `CORTEX_REPO_ROOT` → git → cwd.** R20-clean (single site). Fixes the **guardian** for free (it relies on the env the guardian plist already sets). Weakness alone: depends on the env actually being present at fire time (per-session plist captures it only conditionally). Run-now: unaffected (env unset → unchanged path).
- **B — Thread an explicit `--repo-root` into `start`, populated by the launcher.** Explicit but adds a CLI flag + arg-plumbing surface; the launcher would trust plist `argv[1]` or parse JSON in bash (the degraded-env fragility the codebase avoids). Relocates authority into the launcher (mild R20 dilution). Does not fix the guardian.
- **C — `handle_start` reads `state.project_root` from the `--state` file as the authoritative `repo_path`.** Uses the **already-correct, already-reachable** value (`--state` is always absolute under launchd). Robust regardless of env-snapshot timing. Fixes `repo: null` (null → session `project_root`). Unifies with `runner.py:1440`, which **already** prefers `state.project_root` for the sandbox deny-list. Run-now safe (state was authored from the correct cwd at create). Needs a fallback when `state.project_root` is null/invalid.
- **D1 — set plist `WorkingDirectory`.** One-key plist change, but fixes by *re-trusting launchd CWD* — directly against the ticket's "never trust launchd's CWD/env" and R20. Doesn't fix `repo: null`. Requires rescheduling every pending job. **Rejected** as the mechanism (acceptable only as optional belt-and-suspenders).
- **D2 — converge the three resolvers** (`_resolve_repo_path`, `_resolve_user_project_root`, init's resolver). Right long-term end-state (the divergence *caused* this bug) but over-scoped for a high-priority fix; `common.py` keeps init's resolver separate by spec. **Defer to a follow-up** (solution-horizon).
- **D3 — runner self-resolves from `state.project_root`.** **Rejected** — violates R20 (`runner.py:2393-2395`).

**Recommendation: C (primary) + A (folded in), unified per the Adversarial single-funnel design below; explicitly not D1; D2 deferred.** Precedence: `state.project_root`(valid) → `CORTEX_REPO_ROOT` → `git rev-parse` → `cwd`.

## Test & Verification

- **Coverage gap:** `_resolve_repo_path` is **monkeypatched away in ~40 tests** (e.g. `test_scheduler_e2e.py:227`, `test_cli_overnight_format_json.py:96`, `test_guardian_install.py:216`), so its real git→cwd fallback is **never exercised** — exactly why the `cwd=/` failure slipped CI. The scheduled fire-path is not tested for root resolution. No tests exist for `_is_scheduled_dormant`, `_parse_iso`, or `parse_target_time`'s tz contract.
- **House idioms:** env via `monkeypatch.setenv("CORTEX_REPO_ROOT", …)` / `delenv`; cwd via `monkeypatch.chdir(tmp_path)`; git via swapping module-bound `subprocess.run`/`check_output` or PATH-shimming a fake binary; platform guards via `pytest.mark.skipif(sys.platform != "darwin")` or `sys.platform`-swap; prefer stubbing the macOS surface and testing pure logic platform-agnostically.
- **Bug 1 regression (fire-free):** build a session with `overnight-state.json` carrying a correct `project_root`; `monkeypatch.chdir("/")` (or a non-git tmp dir) + clear `CORTEX_REPO_ROOT`; spy on `runner.run`'s `repo_path` kwarg; call `handle_start` with the scheduled namespace. Assert captured `repo_path == state.project_root`, **not** `/`. **Do not patch `_resolve_repo_path`** (that's what hid the bug). Companion: a direct precedence unit test of the new `_resolve_repo_path(state_project_root=…)`.
- **Bug 2 regression:** call `render_status()` (or `handle_status`) with `phase: "executing"` (the dormant path masks the subtraction) and a **naive-local** `scheduled_start` near a fire boundary under a **non-UTC `TZ`**; assert no crash, correct "fires at"/elapsed, and no `Error reading status:`. Cases: naive-local `scheduled_start`, aware `started_at`, mixed.
- **Manual:** `cortex overnight status` against the failed session (`overnight-2026-06-22-0246`) → renders post-fix. For Bug 1, schedule a fire ~1-2 min out, let launchd fire, then assert `active-session.json` `repo_path` is the real root (not `/`) and no `morning_report_commit_failed details.project_root: "/"`. Review workaround while status is broken: `launchctl list | grep overnight-schedule` + read `overnight-events.log`.

## Adversarial Review

The diagnosis is correct but **understated on three fronts**, and the obvious Bug-2 fix is wrong:

1. **Bug-2 assume-UTC is a correctness bug (verified by arithmetic).** `scheduled_start` is naive-LOCAL; coercing it to UTC in `_parse_iso` skews `fires_at <= now` (`status.py:177`) by the **local UTC offset** (e.g. 4h), rendering future schedules as already-fired or vice-versa. The `_is_spent` precedent attaches **local** tzinfo, not UTC — citing it for assume-UTC inverts what it does. **Correct fix:** per-field — attach the **local** offset to naive `scheduled_start` before compare (and coerce only legacy-naive `started_at`/`ts` to UTC); **or, durably,** fix the writer to emit `scheduled_start` with a local offset (`resolved_target.astimezone().isoformat()`) *and* keep a reader-side naive-local backstop for already-scheduled (legacy) sessions. Never blanket assume-UTC in `_parse_iso`.

2. **The guardian (#308 supervision) is silently broken under launchd by the same defect.** `_dispatch_overnight_guardian_scan` (`cli.py:171`) resolves via `_resolve_repo_path()` → under launchd CWD=`/` → `state_root = /cortex/lifecycle` → finds no sessions → **recovers nothing**. The guardian plist *already* sets `CORTEX_REPO_ROOT` (`macos.py:1175`) expecting it to be honored — but `_resolve_repo_path` ignores env. So **Approach A's env-read is required, not optional**, for supervision to function at all.

3. **The async-spawn child re-resolves independently.** The launcher fires `start --state <abs> --scheduled` (no `--launchd`) → async-spawn path; `_spawn_runner_async`'s `Popen` does **not** set `cwd=`, and the spawn argv carries no repo-root → the child re-invokes `start --launchd --state <abs>` from inherited CWD=`/` and re-runs `handle_start`, re-resolving via `_resolve_repo_path()`. **Fixing only the parent's threaded `repo_path` is insufficient** — the fix must live where both invocations read it (`handle_start` / `_resolve_repo_path`).

4. **`state.project_root` validity guard needed.** It is `Path.cwd()`-defaulted at create (`plan.py:560`) and nullable (`state.py:260`). Guard: if it is `/`, missing, or not a directory, do not trust it — fall through. Correct order: `state.project_root`(valid) → `CORTEX_REPO_ROOT` → `git` → `cwd`.

5. **R20 single-funnel design (the clean shape).** Folding A into C naively creates **two** resolution sites that can disagree (state in `handle_start` vs env in `_resolve_repo_path`, with `runner.py:2503` then re-exporting whichever won). Cleanest: give `_resolve_repo_path(state_project_root: Path | None = None)` the **full precedence inside one function**; `handle_start` passes the loaded `state.project_root`; `cli.py` guardian/recover pass `None`. One function, one precedence — fixes parent, child, and guardian, and preserves R20 literally.

6. **Deployment:** wheel reinstall is **mandatory** (fired binary runs the wheel). With C+A, **no plist regeneration is needed** — Approach C reads `state.project_root` fresh at fire (launcher already passes absolute `--state`), and the guardian plist already ships `CORTEX_REPO_ROOT`, so a wheel reinstall alone fixes both pending scheduled jobs and already-installed guardians. (Verify the guardian was installed post-#308 so its plist carries the var.)

7. **status.py uses a *different* resolver** (`common._resolve_user_project_root`), so its crash is orthogonal to Bug 1 — a pure tz bug, not a root-resolution bug. The two fixes are independent and can land in either order.

Minor: same-user LaunchAgent (`launchctl bootstrap gui/$(id -u)`, `macos.py:690`) makes git dubious-ownership unlikely; the failure is plain `git rev-parse` from `cwd=/`. Consider a `.resolve()` consistency pass if touching `project_root` (symlinked-path equality in `report.py:1773`).

## Open Questions

- **[RESOLVED] Mechanism.** Confirmed: `_resolve_repo_path()` (git→cwd, no env) returns `/` under launchd; `state.project_root` is correct but unread; `runner.py:2503` poisons `CORTEX_REPO_ROOT` for children. The ticket's "CWD/env" framing is imprecise — the primary mechanism is a failed `git rev-parse` falling to cwd.
- **[RESOLVED] Bug 1 fix shape.** Single-funnel `_resolve_repo_path(state_project_root=None)`, precedence `state(valid)→CORTEX_REPO_ROOT→git→cwd`, with a `/`-and-not-a-dir validity guard. `handle_start` passes loaded `state.project_root`; `cli.py` guardian/recover pass `None`. Fixes parent + re-resolving child + guardian at one R20-compliant site.
- **[RESOLVED] Bug 2 fix shape.** Do **not** assume-UTC. Reader: normalize naive `scheduled_start` on its **local** footing at the compare (mirroring `_is_spent`). Spec to decide whether to *also* fix the writer (`macos.py`/`cli_handler.py` emit aware `scheduled_start`) for durability — recommended, but the reader backstop is required regardless for legacy sessions.
- **[DECISION FOR SPEC — scope] Include the guardian fix in #311?** The guardian (#308 supervision) is broken under launchd by the identical defect and is fixed *for free* by the single-funnel `_resolve_repo_path` change (guardian passes `None`, relying on the env its plist already sets). Recommendation: **include it** — leaving a core supervision capability silently non-functional under launchd is indefensible, and the marginal cost is one extra test. Spec will confirm scope; surface at spec approval if the operator prefers a separate ticket.
- **[DECISION FOR SPEC — durability] Writer-side `scheduled_start` fix?** Per solution-horizon, emitting aware `scheduled_start` removes the ambiguity for new sessions, but the reader-side normalization is still needed for already-scheduled (naive) sessions. Recommend doing both; spec to finalize. Confirm whether `_is_spent`'s separate `ScheduledHandle.scheduled_for_iso` writer also needs the change.
- **[VERIFY IN IMPLEMENT — environment] Guardian install vintage.** Confirm the operator's installed guardian plist (if any) carries `CORTEX_REPO_ROOT` (post-#308); if installed earlier, it needs reinstall to benefit from the env-read. Not a design blocker.
