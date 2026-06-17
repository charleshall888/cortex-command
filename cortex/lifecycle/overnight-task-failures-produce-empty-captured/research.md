# Research: Capture and surface failing overnight-runner dispatch metadata (#309)

**Clarified intent:** On a failed overnight task/dispatch, surface the failing worker's diagnostic metadata (stderr tail, exit code, cwd, and a meaningful identity) onto the path the brain's retry/defer decision and the morning report actually consume — instead of an opaque `ProcessError: exit code 1` with empty output.

**One-line conclusion:** The data is already captured at the dispatch layer and then *discarded from the result carrier*. The fix is a deliberate **Hybrid (Approach A)**: thread a single diagnostics bundle through the carriers to feed the brain, and surface it in the morning report via the already-read `task_output` event — **plus a mandatory redaction-broadening precondition** because #309 is the change that makes subprocess stderr human-facing and committed to `main`.

---

## Codebase Analysis

**The gap (verified):** `cortex_command/pipeline/dispatch.py` `dispatch_task()` captures `child_stderr` (via the `_on_stderr` callback; redacts `sk-ant-` keys; capped at `_MAX_STDERR_LINES=100`, **no byte cap**) and `exit_code` (`getattr(exc, "exit_code", None)`) at both error branches (lines ~795–844), and writes them into the `dispatch_error` event in `pipeline-events.log`. But `DispatchResult` (lines 299–318) carries only `success/output/error_type/error_detail/cost_usd` — the stderr/exit_code are **dropped from the result object**. `output` is only joined assistant `TextBlock` text (`"\n".join(output_parts)`), which is empty when a worker crashes before emitting text.

**Files that will change:**
- `cortex_command/pipeline/dispatch.py` — `DispatchResult` (299–318): add diagnostics fields, following the `cost_usd: Optional[float] = None` template. Populate at the 3 return sites from already-computed locals. Add `cwd`/identity to the `dispatch_error` event dict (806–813, 829–836).
- `cortex_command/pipeline/retry.py` — `RetryResult` (42–67): carry diagnostics from the final attempt's `result`. There are ~7 construction sites (292, 342, 370, 392, 420, 453 + the idempotency-skip at `feature_executor.py:665`).
- `cortex_command/overnight/brain.py` — `BrainContext` (60–81): add a diagnostics field; templated in `_render_template` (215–223). The only failure-evidence field today is `last_attempt_output` (79).
- `cortex_command/overnight/prompts/batch-brain.md` — add a diagnostics section near `## Final Attempt Output` (25–29) with matching placeholder.
- `cortex_command/overnight/feature_executor.py` — `_handle_failed_task` `BrainContext(...)` assembly (257–265, defensive-`getattr` idiom); the `task_output` event write (704–710) gains a distinct stderr/exit_code field.
- `cortex_command/overnight/report.py` — `render_failed_features` (1169–1301) per-failure block; extend the existing `**Last worker output**` line (1278–1283) fed by `_read_last_task_output` (1928–1961, **500-char cap**).
- `bin/.events-registry.md` — field-additive extension under `dispatch_error` (line 88) and `task_output` (line 130). **No new event name.**
- Tests: `pipeline/tests/test_dispatch.py`, `overnight/tests/test_report.py`, `test_brain.py`, plus failure-path report fixtures.

**Key architectural insight:** `FeatureResult` (`types.py:18-31`) carries **no** output/cost/stderr fields. The morning report does **not** receive failure detail through the carrier — it re-correlates by reading `pipeline-events.log` filtered by feature (this is how it already surfaces cost via `_aggregate_feature_cost` and worker output via `_read_last_task_output`). So the **report side is event-log-driven** and the **carrier side exists only to feed the brain** (which is handed a constructed `BrainContext`, not the log). This dissolves the A-vs-B fork into a hybrid-by-consumer.

**Conventions:** redaction at source (`_on_stderr`, `re.sub(r'sk-ant-[a-zA-Z0-9_-]+', ...)`) so anything threaded downstream is already `sk-ant-`-scrubbed; reusable `_redact` at `overnight/auth.py:54-59`. Truncation constants per layer: 100 lines capture, `[:2000]` prompt/event, `[:500]` report. Defensive `getattr(result, 'field', default)` for carrier-shape tolerance. Field-additive event extensions, not new event names.

## Web Research

The symptom is **documented upstream SDK behavior**, not a local bug: the SDK raises `ProcessError(..., stderr="Check stderr output for details")` — a hardcoded placeholder — while the real child stderr only reaches you via the `stderr` callback (issues anthropics/claude-agent-sdk-python #834 on v0.1.61, #515). So `ProcessError.stderr` is worthless; `_stderr_lines` (callback-accumulated) is the only real source — the cortex code already does this correctly.

Prior-art patterns:
- **Mirror `subprocess.CalledProcessError`** — the stdlib template attaches `{returncode, cmd, output/stdout, stderr}` to the failure object. Capture is decoupled from raising: *capture always, decide downstream*.
- **Truncation:** tail beats head for failures (the fatal line is at the end). Use a bounded `deque(maxlen=N)` fed by the line callback; enforce a **byte cap** as the hard limit (lines can each be huge), line cap secondary.
- **Redaction:** scrub secret *shapes* by value (`sk-...`, `ghp_`, `Bearer `, key-named fields) **before** the data lands in any sink; provide an over-redaction escape hatch (Pydantic Logfire, `loggingredactor` patterns). Decode with `errors="replace"` to keep the diagnostic path from itself throwing on binary/partial-UTF-8 output.
- **Structured failure-context propagation:** Celery stores the exception+traceback on the result backend (warning: context on custom attributes can be lost in serialization round-trips — put diagnostics on the carrier, not exotic exception attrs); LangGraph embeds error metadata in graph state for the decision layer. Both reinforce: **attach failure context as a first-class field on the carrier the decision layer reads**, not a side log.

## Requirements & Constraints

- **`dispatch_error` already exists in `bin/.events-registry.md`** (line 88) and already carries `child_stderr`+`exit_code`. Adding `cwd`/identity is a **field-additive schema extension** under the owning event (registry lines 146–153: optional fields, emitters omit when `None`, consumers tolerate absence) — **not a new event-name row**.
- **Failure-surfacing is the north-star requirement** (`project.md` Philosophy: "Surface failures in the morning report"); `pipeline.md` audit-trail requirement governs the append-only JSONL log. `pipeline-events.log` rides the append path (`log_event`), not the atomic-replace path (that binds `overnight-state.json`/deferral files).
- **Redaction discipline is a hard, already-implemented constraint** (`_on_stderr`, `sk-ant-` scrub + 100-line cap). Any new capture must route through the same discipline. There is no separate `docs/policies.md` clause (that covers tone only) — the redaction rule lives in code.
- **No mirror/parity regen:** `cortex_command/` is **not** mirrored into any plugin (the dual-source hook covers `skills/`, `hooks/`, `bin/` only). Pure Python edits here incur no `build-plugin` step.
- **Wheel-vs-working-tree:** `just test` runs the editable install — verify against the working tree; `CORTEX_COMMAND_FORCE_SOURCE=1` forces source. (Matches the project memo: prefer sequential dispatch over worktree for `cortex_command` edits.)
- **Lifecycle required:** complex+high places this on the lifecycle track (review-gated).
- **Tests that bind:** `pipeline/tests/test_dispatch.py` + `test_metrics.py` (`pair_dispatch_events` keys on event *type*, not field presence — field additions are safe), `tests/test_morning_report.py`/`test_report.py` (`render_failed_features` already renders `**Last worker output**`), `tests/test_runner_pr_gating.py` byte-identical `dry_run_reference.txt` snapshot, `test_feature_executor.py`. Any `grep -c` Done-When must name real tokens (`tests/test_backlog_grep_targets_resolve.py`).

**Scope boundary (#309 vs #308) is clean and mutual:** #309 = per-failure **content capture**; #308 = **supervision/halt/liveness**. Each names the other's deliverable as its explicit non-goal. #258 abandoned; #262 complete (aggregates the *signal*; #309 captures the *content*).

## SDK Capture Boundary

`claude_agent_sdk` **v0.1.46** (pinned `>=0.1.46,<0.1.47`). Confirmed against installed source:
- **No stdout callback exists.** `ClaudeAgentOptions` has exactly one output callback: `stderr: Callable[[str], None]`. Child stdout *is* the `--output-format stream-json` JSON message channel, consumed internally. There is **no zero-cost way to capture raw child stdout**; `output_parts` (assistant text) is the only proxy and is empty in the crash-before-text case. Capturing "stdout tail" would require enabling partial-message streaming — out of proportion to the need.
- **`ProcessError`** has `exit_code: int | None` (real, trustworthy) and `stderr` (hardcoded placeholder — ignore). The single raise site (transport) attaches no argv.
- **CLI argv is built then discarded** — the literal failing command is unrecoverable from the exception.

**Per-artifact verdict:**
| Artifact | Verdict | Source |
|---|---|---|
| stderr tail | **FREE** | `_stderr_lines` (capped, `sk-ant`-redacted) |
| exit code | **FREE** (but `None` for `CLIConnectionError`/`TimeoutError`) | `ProcessError.exit_code` |
| cwd | **trivial add** | `str(worktree_path)` (already passed as `cwd=`) |
| command | **redefine or defer** | literal argv unavailable; only the SDK invocation descriptor (feature/skill/attempt/model/effort) is available — and that is NOT the failing inner command |
| stdout | **not available** | no SDK stdout callback |

Worst-case undiagnosable state: the `CLIConnectionError` path ("Working directory does not exist" / "Failed to start Claude Code") where `exit_code=None` and stderr is often empty — there, the invocation identity (`feature/skill/attempt/cwd`) is the only thing that rescues it.

## Consumer Contract & Diagnostic Value

**Brain contract:** `batch-brain.md` gives the brain exactly one failure channel — `## Final Attempt Output` (`{last_attempt_output}`), which the prompt tells it to use "to understand exactly what went wrong" and to cite in `reasoning`. There is no exit-code/cwd/stderr section. The PAUSE guidance asks it to recognize "a transient infrastructure issue" with no field to distinguish infra-transient from logic-defect — exactly the distinction the incident brain had to *guess*. Assembly: `feature_executor.py:263` → `BrainContext.last_attempt_output` ← `RetryResult.final_output` ← `DispatchResult.output` (empty on crash).

**Report contract:** `render_failed_features` (report.py:1169) renders `**Last worker output**` via `_read_last_task_output` (reads `task_output` event, 500-char cap). Precedent for surfacing an exit code already exists: `render_tool_failures` renders `last exit code: 1` via `_read_last_exit_code`.

**Diagnostic-value verdict (re-scoped per adversarial):** For **ProcessError-class** failures, exit_code + cwd + (named step) materially moves ~4 of 5 classes from "opaque exit 1" toward "localized + attributable" — strongest for code-defect (stderr carries the assertion/compiler error), pre-commit-gate (names the commit step), and crash (exit-code-typed). For the **silent-crash class that motivated the ticket** (output empty AND stderr empty AND exit 1-or-None), #309 yields a **better-labeled unknown** — an explicit "stderr was empty" marker + cwd that distinguishes "silent crash" from "ran but said nothing" — **not a diagnosis**. Still worth shipping; the framing must not oversell. The genuinely silent `worker_no_exit_report` case is out of scope (no `DispatchResult` at all).

## Tradeoffs & Alternatives

- **Approach A (extend carriers):** single producer, in-memory correlation, zero retry-row ambiguity (`RetryResult` already holds "the last attempt"), matches the dominant `error_type`/`cost_usd`-threading idiom. Cost: ~7 `RetryResult` sites — miss one and that path silently carries empty stderr.
- **Approach B (consumer re-correlates event log):** zero new fields, matches the report's log-scan idiom — **but genuinely fragile**: `dispatch_error` has **no `task_number`** (only `feature`), the only existing correlator (`metrics.pair_dispatch_events`) already `warnings.warn`s "orphan dispatch_error", retry rows interleave under concurrency, and the **brain consumer is mid-run** (read-your-own-writes race on a log it's actively writing).
- **Recommended — Hybrid:** A for the brain (deterministic, no race); for the report, extend the **`task_output`** event (which *does* carry `task_number` and is written by `feature_executor` from the carrier) so the existing `_read_last_task_output` path surfaces it — avoiding the fragile `dispatch_error` reader. Keep the `dispatch_error` event write as a second intentional forensic/metrics sink (one-line comment so a future reader doesn't "DRY it away" and reintroduce the bug).
- **Approach-independent hardening:** add a **byte cap** in `_on_stderr` (today's 100-*line* cap lets a single 10 MB line through into log + prompt + report); **broaden redaction** beyond `sk-ant-` (value-level, not whole-line).

Cost matches value: complex-tier is correct (three dataclasses across two packages, a hot `asyncio.gather` path, an LLM prompt + a human artifact, and redaction/truncation policy with leakage stakes), and the incident shows a 4×-recurring undiagnosable failure where the brain explicitly guessed.

## Cross-Ticket Coordination

- **#308 surfaces** (mostly non-overlapping with #309): `_SESSION_HALT_ERROR_TYPES` (`feature_executor.py:75`), the `worker_no_exit_report` emit + zero-commits gate (`feature_executor.py:857-873`), orchestrator halt checks (`orchestrator.py:406-429, 508-522`), the systemic cascade (`outcome_router.py`, `_SYSTEMIC_ERROR_TYPES`/`SYSTEMIC_FAILURE_THRESHOLD=3` in `constants.py`), and out-of-process liveness/`runner.pid` in `runner.py`.
- **Sharpest collision risk:** `error`/`error_type` semantics. #308 needs `result.error` as a **closed-vocabulary halt token** (checked `in _SESSION_HALT_ERROR_TYPES`/`_SYSTEMIC_ERROR_TYPES`). #309 must **never overload `error`/`error_detail`** with free-text — add **parallel structured fields**. Honor #262's spec invariant: `error` stays the single string channel for halt/systemic consumers.
- **Field namespace:** reuse the names already live in dispatch.py (`child_stderr`, `exit_code`) + `cwd`; consider grouping into one nested diagnostics object so #308 (or a future #262 Slice-B) can read exit_code/stderr for classification.
- **Landing order: #309 first** — additive, low blast radius; once landed it gives #308 richer inputs. The two hot lines (`dispatch.py:795-844`, `feature_executor.py:857-873`) should be coordinated in one branch if near-simultaneous.
- **Crucial scoping fact:** the `worker_no_exit_report` branch has **no `DispatchResult`** (dispatch succeeded; detected by exit-file absence) — #309's fields do **not** cover #308's incident driver. (Also flagged for the #308 implementer, out of #309's lane: #308's premise that #262 added `worker_no_exit_report` to `_SESSION_HALT_ERROR_TYPES` is inaccurate — #262 shipped a zero-commits-gated pause + a separate cascade counter that never tripped on mid-feature events.)

## Adversarial Review

1. **Active leakage surface (real, not hypothetical).** `cortex/.gitignore` ignores `overnight-events*.log` and `metrics.json` but **not** `pipeline-events.log` — it is tracked and was snapshot-committed in `9323efea`. The morning report is `git add`/committed to local `main` by `runner.py:_commit_morning_report_in_repo`, and **#129 is deliberately un-silencing that commit**. #309 routes subprocess stderr (only `sk-ant-` redacted) into the human-facing report line and the committed log. `ghp_`/`Bearer `/`password=`/`https://user:pass@host`/AWS patterns all pass through today. → **Redaction-broadening is in-scope for #309 by causation; the `pipeline-events.log` tracking question must be resolved explicitly (gitignore it, matching the `overnight-events*.log` precedent, or document acceptance).**
2. **`task_output` is emitted UNCONDITIONALLY on the failure path** (`feature_executor.py:704-710`, not nested under `if result.success`) and carries `task_number` — Proposal #2 holds. Caveats: stderr must be a **distinct** field (not `output`, which is empty on crash → two independent plumbings of the same data), and `_read_last_task_output`'s **500-char cap** would clip the stderr tail — needs a deliberate re-budget.
3. **`exit_code` is `None` for `CLIConnectionError`/`TimeoutError`** — the "free win" is partial; re-scope the diagnostic-value claim to ProcessError-class.
4. **~7 `RetryResult` sites fail silently if one is missed** → carry **one `last_dispatch_diagnostics` bundle** (set once from the final `result`), not three parallel scalars; add a test asserting every failure-path exit propagates it.
5. **`command` descriptor is the strongest mislead risk** — labeling the SDK invocation descriptor as "command" invites the brain to blame the `implement` invocation when the failure was a pre-commit hook three layers down. **Defer `command`** (or label it unambiguously as SDK invocation params).
6. **`exit_code`/empty-stderr over-trust** — exit 1 is generic; frame in the prompt with limits (generic-1, None-on-timeout, empty-as-silent-crash-not-localized).
7. **Tests:** `pair_dispatch_events` keys on type (safe) but the codebase uses field-presence (`_DAYTIME_DISPATCH_FIELDS`) as a schema discriminator — new names don't collide; add a one-line guard test. Regolden failure-path fixtures (`test_morning_report.py`, `test_runner_morning_report_commit.py`); `dry_run_reference.txt` is a success path (likely unaffected — verify).

## Open Questions

1. **Redaction breadth + `pipeline-events.log` git-tracking — scope decision for the user.** Research strongly recommends broadening `_on_stderr` redaction beyond `sk-ant-` (value-level: `ghp_`/`gho_`/`ghs_`, `Bearer `, `password=`/`token=`, `https://user:pass@host`, common AWS/`xoxb-`) **in #309**, because #309 is the change that makes subprocess stderr human-facing and committed to `main` (worsened by #129 un-silencing the report commit). Open sub-question: also gitignore `pipeline-events.log` (matching `overnight-events*.log`), or document acceptance? *Deferred: resolved in Spec by asking the user — this is a scope/posture decision (in-scope hardening vs. separate ticket) and a security-policy call, not an evidence-determined one.*
2. **Byte cap in `_on_stderr` — in-scope for #309 or separate?** Cheap (same edit site), closes a pre-existing 10 MB-single-line hole that already affects the event log. Recommendation: include in #309. *Deferred: resolved in Spec by asking the user (scope-boundary decision).*
3. **Report stderr-tail truncation re-budget.** `_read_last_task_output` caps at 500 chars; the stderr tail must be a distinct `task_output` field with its own (larger) cap, or the most diagnostic part is clipped. *Resolved: store stderr as a distinct `task_output`/diagnostics field with a deliberate tail cap (proposal: a stderr-specific budget larger than 500, tail-anchored); the exact number is a spec detail.*
4. **Carrier shape — bundle vs. scalars.** *Resolved: carry one `last_dispatch_diagnostics` object (child_stderr, exit_code, cwd) set once from the final attempt's `DispatchResult`, threaded as a single optional field through `RetryResult` and read by a single `getattr` — lower silent-drop risk than three scalars across ~7 sites; add a test covering every failure-path exit.*
5. **`command` artifact — drop, defer, or surface-with-label?** *Resolved: defer the literal `command` (unrecoverable from the SDK and a brain-mislead risk). If any identity is surfaced, label it explicitly as SDK invocation parameters, not the failing inner command. The ticket's "exact command" is reinterpreted as cwd + the already-present invocation identity (feature/skill/attempt).*
6. **`stdout` artifact.** *Resolved: drop from scope — SDK v0.1.46 exposes no stdout callback; capturing raw stdout would require enabling partial-message streaming, disproportionate to the need. The ticket's "stdout/stderr tail" reduces to stderr tail.*
7. **Diagnostic-value framing for the brain prompt.** *Resolved: frame exit_code/stderr with their limits (exit 1 generic; None on timeout/connection; empty-stderr = "silent failure" marker, not a localized diagnosis) so the brain neither over-trusts a generic code nor under-weights the learnings file. The originating silent-crash class gets a better-labeled unknown; the `worker_no_exit_report` class is explicitly out of scope (#308).*

## Considerations Addressed

(Not applicable — no `research-considerations` were injected; clarify-critic raised no parent-epic alignment findings, so none propagated.)
