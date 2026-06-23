# Research: claude_agent_sdk 0.1.46 bundles a stale claude CLI (2.1.69) that hard-rejects `--effort xhigh`, failing every complex/high|critical overnight dispatch (#313)

> **Note on the ticket's evolution.** Backlog #313 was rewritten mid-research. Its *original* root cause (a `_TIER_MATRIX` capping the model to Sonnet, with `resolve_effort` validating the pre-cap model) was investigated and **disproven** — there is no `_TIER_MATRIX`, `--tier` is concurrency-only, and the dispatch model was correctly `opus`. The *current* ticket (and this research) centers on the **stale bundled CLI inside the SDK**. The lifecycle slug `overnight-dispatch-sends-opus-only-xhigh` predates the rename and is retained for continuity; it is linked to the renamed backlog file by UUID and `lifecycle_slug`.

## Root Cause (Confirmed — firsthand reproduced)

The single most important deliverable: the exact failing invocation and why it fails.

**Chain:**
1. cortex correctly resolves the dispatch as **`model=opus, effort=xhigh`** for the `(complex,high)` and `(complex,critical)` cells. `cortex_command/pipeline/dispatch.py:146` `_MODEL_MATRIX[("complex","high")]="opus"`; `dispatch.py:168` `_EFFORT_MATRIX[("complex","high")]="xhigh"`. This pairing is internally valid (`_MODEL_SUPPORTED_EFFORTS["opus"]` includes `xhigh`, `dispatch.py:188`), so `resolve_effort`'s guard (`dispatch.py:281-287`) passes.
2. `dispatch_task` builds `ClaudeAgentOptions(model="opus", effort="xhigh", …)` (`dispatch.py:768-780`) and hands it to the SDK `query()`. The SDK transport renders both as raw CLI flags — `--model opus` and `--effort xhigh` — with **no model/effort reconciliation** (`claude_agent_sdk/_internal/transport/subprocess_cli.py:207-208, 315-316`).
3. The SDK chooses **which `claude` binary to spawn** via `_find_cli()` (`subprocess_cli.py:64-72`): it returns the **bundled** CLI *first* (`_find_bundled_cli()`, lines 67-69), only falling back to `shutil.which("claude")` (line 72) if no bundled binary exists.
4. The bundled binary in `claude_agent_sdk 0.1.46` is **claude-code 2.1.69** (a 197 MB binary at `.venv/lib/python3.13/site-packages/claude_agent_sdk/_bundled/claude`, dated May 5 2026). Version 2.1.69 **predates `xhigh`** — its `--effort` vocabulary is exactly `{low, medium, high, max}` and it **hard-errors** (commander.js arg validation) on `xhigh`.
5. cortex passes **no `ClaudeAgentOptions(cli_path=…)`** anywhere (`dispatch.py:768`, `discovery.py:724` — verified), so nothing redirects the SDK to the newer system CLI.

**Net effect:** `opus + xhigh` dispatch → SDK spawns bundled 2.1.69 → instant `exit 1` arg-rejection → classified `task_failure` → feature paused. Every `(complex,high)`/`(complex,critical)` implement **and review** dispatch dies this way, regardless of model.

**Byte-identical reproduction (run firsthand in this repo's `.venv`):**
```
$ env -u CLAUDECODE .venv/.../claude_agent_sdk/_bundled/claude --effort xhigh --version
error: option '--effort <level>' argument 'xhigh' is invalid. It must be one of: low, medium, high, max
$ env -u CLAUDECODE .venv/.../claude_agent_sdk/_bundled/claude --effort high  --version
2.1.69 (Claude Code)
$ env -u CLAUDECODE claude --effort xhigh --version     # system: ~/.local/bin/claude
2.1.186 (Claude Code)                                    # ACCEPTS xhigh — exit 0
```

**Ground-truth log (from the actual failing run, in the consuming repo):**
`/Users/charlie.hall/Workspaces/wild-light/cortex/lifecycle/sessions/overnight-2026-06-23-0605/pipeline-events.log` records the failing `dispatch_start` as `complexity: complex, criticality: high, model: opus, effort: xhigh`; the `sonnet + high` (simple) tasks in the same run ran for minutes and succeeded. **The failing model was `opus`, not Sonnet.**

**Governance fact:** `pyproject.toml:10` pins `claude-agent-sdk>=0.1.46,<0.1.47` — a hard pin to 0.1.46. Per the "Distributed-CLI dependency bounds" constraint (`cortex/requirements/project.md:47`), `uv tool install` from a git ref ignores `uv.lock`, so this `pyproject` bound is the *only* governance reaching every install. Latest on PyPI is **0.2.107**.

---

## Codebase Analysis — Dispatch Path & CLI/SDK Effort Wiring

- **Implement path:** `feature_executor.py:687` `retry_task(...)` → `retry.py:264` `dispatch_task(model_override=current_model, skill="implement")` → `dispatch.py:641-642` resolves model/effort → `dispatch.py:768-780` `ClaudeAgentOptions(model=…, effort=…)` → SDK `query()` → `subprocess_cli.py` builds argv.
- **Flag rendering (SDK):** `subprocess_cli.py:207-208` `if self._options.model: cmd.extend(["--model", model])`; `:315-316` `if self._options.effort is not None: cmd.extend(["--effort", effort])`. Raw pass-through, no validation.
- **CLI selection (SDK):** `_find_cli()` (`subprocess_cli.py:64-72`) → `_find_bundled_cli()` first (`:97-110`), then `shutil.which("claude")`, then a fixed fallback list (incl. `~/.local/bin/claude`). `cli_path` override is honored when set (`:46-47`).
- **Every `dispatch_task` call site (verified, with effort outcome on bundled 2.1.69):**

  | Call site | complexity | criticality | model | effort | bundled-CLI verdict |
  |---|---|---|---|---|---|
  | `retry.py:264` (skill=implement) | task.complexity | feature crit | resolve/escalation | matrix | **FAILS** at (complex,high\|critical) → xhigh |
  | `review_dispatch.py:264` (review) | feature | feature | matrix | matrix | **FAILS** at (complex,high\|critical) → xhigh |
  | `review_dispatch.py:401,516` (review-fix) | feature | feature | matrix | `max` (skill override on opus) | safe (max accepted) |
  | `conflict.py:349` (conflict-repair) | `simple` | medium | sonnet | high | safe |
  | `merge_recovery.py:340` (merge-test-repair) | `simple` | medium | sonnet/opus | high | safe |
  | `integration_recovery.py:216` | `complex` | medium | `opus` | high→`max` | safe |
  | `brain.py:280` (brain) | `simple` | medium | — | high | safe |
  | `discovery.py:724` | — | — | sonnet | *(no effort kwarg)* | safe |

- **Guard is on the live path, not bypassed:** `dispatch.py:641-642` resolves effort against the *same* model dispatched; the `effort_override` parameter exists (`dispatch.py:556`) but **no caller passes it** (verified exhaustively). So the in-process guard always runs — but it validates **model capability**, which is the wrong axis (see Adversarial / Open Questions).

## Codebase Analysis — Model Resolution (the matrices are correct; there is no Sonnet downgrade)

- `read_criticality` (`cortex_command/common.py:530-553`) defaults to `medium` when absent, but the run recorded `high` — not implicated.
- Per-task complexity: `parser.py:396` `_parse_field_string(task_body,"Complexity") or "simple"`; OOV → normalized to `complex` (`:397-401`).
- Model and effort both derive from the **same** `(complexity, criticality)` pair at `dispatch.py:641-642`; they cannot diverge via the matrices. The only two cells producing `xhigh` — `(complex,high)`/`(complex,critical)` — both map to `opus`. **There is no `(complexity,criticality)` pair yielding `sonnet+xhigh`.**
- No global/forced/default model in the overnight path; `_env` (`dispatch.py:651-670`) sets no `ANTHROPIC_MODEL`. The retry escalation ladder (`retry.py:223,273`; `MODEL_ESCALATION_LADDER` haiku→sonnet→opus) only escalates *upward* and re-resolves effort per attempt.
- **No `_TIER_MATRIX` exists** (`git log -S _TIER_MATRIX` empty). `--tier {simple,complex}` (`cli.py:609-613`) flows to `cortex-batch-runner --tier` → `throttle_tier` → `load_throttle_config` (`throttle.py`: tiers `max_5/max_100/max_200`; `simple` falls back to MAX_100) → **concurrency only**, plus the orchestrator-round telemetry label (`runner.py:2812`). It never selects the per-feature model. The original ticket's mechanism does not exist in the code.

## Web Research — claude_agent_sdk effort/model wiring & per-model vocabularies

- The SDK's `ClaudeAgentOptions` carries `effort` and `model`; the transport maps them to `--effort`/`--model` **raw, with zero reconciliation** (confirmed against the published SDK source). Validation is the caller's responsibility on the flag path.
- Per-model effort vocabulary (authoritative — Claude Code model-config + API effort docs): `xhigh` is **only** Fable 5 / Opus 4.8 / Opus 4.7. **Opus 4.6 and Sonnet 4.6 both support exactly `{low, medium, high, max}`** — so an accepted set of `{low,medium,high,max}` does **not** uniquely identify Sonnet (the ticket's original inference was unsound; the real reason that set appears is the *stale CLI's* vocabulary).
- The `--effort` *flag* path **hard-rejects** unsupported values (commander.js); the *interactive `/effort` / settings* surface clamps ("falls back to highest supported ≤ requested"). The codebase comment at `dispatch.py:592` ("`xhigh` … is silently downgraded by non-Opus models") describes the **wrong surface** — the SDK uses the flag path, which rejects. SDK issue #834 is an exact match for this symptom (opaque `ProcessError` on a CLI-rejected flag).

## Requirements & Constraints

- **Fail-loud convention** (`project.md` Quality Attributes; `pipeline.md` "fail the feature loudly rather than degrading silently"; `parser.py:352,470` precedent) — a model/effort/CLI mismatch should surface clearly, not silently degrade. The escalation ladder is explicitly **no-downgrade** (`docs/overnight-operations.md:373`).
- **Distributed-CLI dependency bounds** (`project.md:47`) — the `pyproject` `[project.dependencies]` bound is the only governance reaching every install; a fix that changes the SDK version **must move that bound**, and the fresh-resolve route smoke test (`cortex_command/dashboard/tests/test_routes_smoke.py`, run in `validate.yml`) is the anti-revert guard for the web stack the bump could disturb.
- **MUST-escalation / "prescribe What not How"** (`CLAUDE.md`) — a code-level `ValueError` guard is not a prose MUST-escalation, so it's unaffected; but the fix should describe the gate/intent, not over-prescribe method.
- **Existing test contracts a fix must preserve** (`cortex_command/pipeline/tests/test_dispatch.py:1042-1265`): `test_effort_matrix_policy`, `test_effort_skill_overrides`, `test_effort_value_passthrough`, `test_effort_runtime_guard_rejects_unsupported_effort_for_model`, `test_resolve_model_raises_on_directly_passed_unknown_tier`, `test_normalized_plan_never_triggers_resolve_model_guard`. (These cover the **model-capability** guard; none cover **CLI-capability** or CLI selection — the actual bug dimension.)
- **Scope:** the original ticket's secondary observations are split out — the review-gate merge-revert is now **#314** (its own lifecycle dir exists). #313 is cleanly scoped to the bundled-CLI/effort-dispatch defect. Per the Adversarial finding, the defect's true blast radius (implement **and** review dispatch, plus the retry/escalation budget burn) is the *same* root cause and belongs in #313.

## Tradeoffs & Alternatives — Remediation

Five candidate levers (the ticket lists 1–4; #5 is the structural fix the Adversarial pass surfaced):

- **(1) Upgrade `claude-agent-sdk`** (bump `pyproject` bound off `<0.1.47`). **Verified working**: 0.2.107 bundles claude-code **2.1.186** (accepts `xhigh`), and all `ClaudeAgentOptions` fields cortex uses (`model, effort, settings, system_prompt, allowed_tools, max_turns, max_budget_usd, cli_path, include_partial_messages, stderr`) still exist — no API break for cortex's surface. **Cons:** 0.2.107 is PyPI-classified **alpha** (~60 releases across a minor bump); wheel grows ~59 MB→65 MB; and `_find_cli` still prefers bundled-first, so the bundled CLI **lags system again over time** → recurrence on the next `xhigh`-class need. A snapshot patch, not structural.
- **(2) Pin `cli_path`** to the system claude (or prefer newer-of-bundled-vs-system). **Pros:** decouples cortex from the bundled-CLI lag and **unifies the CLI** the orchestrator spawn (`runner.py:1482`, uses system `claude` via PATH today) and the SDK worker use — closing a real **version skew**. Settings-tempfile interaction is clean (`cli_path` only sets `cmd[0]`). **Cons:** reintroduces a hard dependency that system claude is present, current, and on the **launchd PATH** (the orchestrator already relies on `~/.local/bin` being on PATH; verify before trusting it); and system 2.1.186 **warn-and-continues** on a genuinely-bad effort (degrades to *default*, not max), weakening the fail-loud contract from the CLI side.
- **(3) Capability preflight + clamp** (`xhigh→max/high` if the CLI doesn't support it). **Rejected as primary** by the Adversarial pass: the probe (`<cli> --effort xhigh --version`) **cannot distinguish "supported" from "silently ignored"** (on a modern CLI, both a valid and a bogus effort exit 0 with a warning); the nested-session guard breaks the probe unless `CLAUDECODE` is cleared; `--help` under-reports the accepted set; and silent clamping degrades the flagship work (fail-loud tension).
- **(4) Surface the real error.** **Mostly already shipped by #309** — `DispatchDiagnostics.child_stderr`/`exit_code` (`dispatch.py:307-314`, `_stderr_lines` 753-766) already capture the CLI's `--effort` error and thread it to the morning report. The only residual gap is `learnings/progress.txt` still showing opaque `ProcessError: exit code 1`. De-scope to a one-line surfacing tweak.
- **(5) Close the category error (structural).** The deepest locus: `_MODEL_SUPPORTED_EFFORTS` describes the **model**, but the **CLI** is what rejects. The guard validates the wrong thing. The durable fix makes effort validation key off the *effective CLI's* accepted set (or the intersection of model-set ∩ CLI-set), so the bug cannot recur on the next bundled-CLI drift. (Tension: the reliable-probe problem from (3) means "key off the CLI set" is non-trivial; the practical durable form may be "pin one known-good CLI (2) so model-set and CLI-set are guaranteed to agree.")
- **(6, independent) Non-retryable classification for arg-rejection.** `classify_error` (`dispatch.py:521`) maps a `--effort`-invalid `ProcessError` to `task_failure → retry`, so the retry loop **re-sends a deterministically-failing flag until the budget is exhausted**. Mapping argument-rejection to a non-retryable type is a cheap, high-value fix independent of the primary lever.

**Synthesis recommendation (to be confirmed in Spec):** the lowest-risk *immediate* fix is **(1) with a sane bound** (e.g. `>=0.2.107,<0.3`, not a hard re-pin), verified compatible. But (1) alone is a snapshot patch — the solution-horizon principle favors pairing it with a **structural** lever so the next bundled-CLI lag doesn't re-trigger: either **(2) pin `cli_path`** (also kills the orchestrator/worker skew) or **(5) fix the guard's data source**. **(6)** should land regardless (stops budget burn). **(4)** is a one-liner. The choice among (1)/(2)/(5) and how far to go is the central Spec decision.

## Prior Art & Design Intent (#090 / #089)

- #090 (`adopt-xhigh-effort-default-for-overnight-lifecycle-implement`) introduced the `xhigh` default, `_EFFORT_MATRIX`, `_MODEL_SUPPORTED_EFFORTS`, and the `resolve_effort` `ValueError` guard. The guard was **deliberately** a fail-loud backstop — but designed under the **false premise that the matrix made `sonnet+xhigh` unreachable** (so it was only ever a defensive future-regression guard). A **clamp was never considered** for the matrix path.
- The "silently downgraded by non-Opus" belief (`dispatch.py:592`) came from an **unverified reading of Anthropic docs** in #090's own research and shipped contradicting `_MODEL_SUPPORTED_EFFORTS["sonnet"]`. #090 did **not** anticipate that the SDK bundles and prefers its own (potentially stale) CLI — the entire design assumed the dispatched CLI tracks the model's documented capabilities.
- #089 (cost study, closed wontfix): `xhigh` scoped to the two Opus cells per Anthropic's "start with xhigh for coding" guidance + a ~1.5× cost estimate. `max` was the pre-`xhigh` ceiling and is universally accepted — relevant if a fix considers `max` as the safe fallback.

## Runtime Evidence

- The decisive `pipeline-events.log` lives in the **consuming repo** (`/Users/charlie.hall/Workspaces/wild-light/cortex/lifecycle/sessions/overnight-2026-06-23-0605/`), not this repo (session artifacts are gitignored here). It confirms the failing dispatch was `model: opus, effort: xhigh` (complex/high), and the simple/sonnet tasks succeeded — establishing the model-was-opus fact empirically.
- `learnings/progress.txt`: `Error: task_failure: ProcessError: Command failed with exit code 1`; feature paused after 2 attempts (the budget-burn symptom).

## Adversarial Review (high/critical — always-last pass, firsthand-verified against the 0.2.107 wheel)

- **Blast radius understated:** the **review** dispatch breaks identically for complex/high|critical; the **retry/escalation** path re-derives `xhigh` and re-fails, and (because arg-rejection classifies as retryable) **burns the retry budget**.
- **Boundary confirmed:** bundled 2.1.69 accepts exactly `{low,medium,high,max}`; only `(complex,high)`/`(complex,critical)` for `skill ∈ {implement, review}` produce `xhigh`. review-fix/integration-recovery (`max`), conflict/merge (`simple`→high), discovery (no effort), orchestrator-round (never xhigh) are all safe.
- **Version skew is structural:** orchestrator spawns system `claude` (2.1.186) via PATH; SDK workers use the bundled CLI. `_find_cli` prefers bundled-first in **both** 0.1.46 and 0.2.107, so upgrading only makes them agree *at the pin moment* — the skew re-opens as system claude auto-updates.
- **FIX 1 compatibility verified** (downloaded 0.2.107: bundled = 2.1.186, `xhigh` accepted, all cortex-used fields present, effort→`--effort` rendering unchanged) — but **alpha** stability.
- **FIX 3 probe unreliable** (cannot distinguish supported vs silently-ignored; nested-session guard; `--help` lies). **FIX 4 mostly redundant** (#309 already captures the stderr).
- **MUST-verify before implementing:** (a) move the **pyproject** bound, not uv.lock; (b) run `test_routes_smoke.py` (fresh-resolve) + full `just test`; (c) confirm the SDK message-type imports (`AssistantMessage`, `ResultMessage`, `ProcessError`, … `dispatch.py:22-33`) resolve in 0.2.x; (d) confirm the launchd PATH includes `~/.local/bin` before relying on system-CLI resolution (FIX 2).

## Contradictions Resolved (firsthand)

1. **"System claude 2.1.186 rejects `xhigh`"** (claimed by the model-resolution agent) vs **"only the bundled 2.1.69 rejects; system accepts"** (operator's repro + Adversarial agent). **Resolved firsthand:** I ran both binaries in this repo's `.venv` — system 2.1.186 **accepts** `xhigh` (exit 0); bundled 2.1.69 **rejects** it. The bundled-CLI explanation is correct. This is load-bearing: because current system claude already supports `xhigh`, making cortex use the system CLI (FIX 2) or a newer bundled one (FIX 1) resolves the bug — the effort level itself is fine on current tooling.
2. **"`resolve_effort` is untested"** (Tradeoffs + Adversarial) vs **"guard tests exist"** (Requirements). **Resolved firsthand:** two unrelated `test_dispatch.py` files exist; the effort/guard tests are at `cortex_command/pipeline/tests/test_dispatch.py:1042-1265`. They cover the **model-capability** guard but **not** the CLI-capability dimension or CLI selection — the actual bug is untested.

## Open Questions

All items below are genuine design choices deferred to the **Spec structured interview** (this is a lifecycle, not standalone refine); the diagnosis itself is fully resolved.

1. **Primary remediation strategy.** **Deferred to Spec.** Which lever(s): (1) upgrade the SDK bound only; (2) pin `cli_path` to the system claude; (5) restructure the guard to key off the CLI's effective set; or a combination? Research recommends **(1) with a sane bound** for the immediate fix **+** a structural lever — (2) pin `cli_path` is favored because it *also* eliminates the orchestrator/worker version skew — plus **(6)** non-retryable classification. The user's risk tolerance for alpha SDK vs system-CLI dependency is the deciding input.
2. **How far on the solution horizon.** **Deferred to Spec.** Is the durable structural fix ((2) or (5)) in scope now, or is the SDK bump sufficient with the structural fix as a named follow-up? The Adversarial pass argues bundled-lag is structural (recurs); the simplicity default argues against over-building. This is the core scope decision.
3. **Bound shape for `claude-agent-sdk`.** **Deferred to Spec.** `>=0.2.107,<0.3` (allows patch/minor within 0.2, drift risk) vs a hard `==` re-pin (freezes the snapshot lag again) — reconcile with the "Distributed-CLI dependency bounds" cap-at-next-breaking-major guidance.
4. **Include the review + retry-budget-burn scope explicitly?** **Deferred to Spec (recommend yes).** Same root cause; the spec should state that the fix covers implement **and** review dispatch and adds the non-retryable arg-rejection classification.
5. **Fail-loud vs run-degraded when a CLI genuinely lacks the matrix effort.** **Deferred to Spec.** If a future/operator environment can't provide an `xhigh`-capable CLI, should cortex fail the feature loud (preserve the no-downgrade posture) or clamp to `max` and surface a visible morning-report note? (Pure silent clamp is rejected by the fail-loud convention.)
6. **Empirical:** the ground-truth `pipeline-events.log` is in the `wild-light` repo, not this one. **Resolved** for diagnosis (model=opus confirmed); no further action needed unless Spec wants the raw lines quoted.
