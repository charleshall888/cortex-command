# Research: Harden overnight review agent's review.md artifact-write adherence (#319)

> **Headline finding — this changes the ticket.** The #319 premise ("the review agent never wrote
> `review.md`; it likely emitted its review as a final chat message") is **contradicted by the
> incident evidence**. The review agent *did* write a complete, valid `review.md` carrying an
> `APPROVED` verdict — it wrote it to the **worktree** directory, where the gate never looks. The
> verified root cause is a **worktree-vs-main path-contract divergence** in the *worktree-mode
> overnight review gate*, not an artifact-write adherence failure. Consequently **three of the four
> candidate mechanisms in the ticket** (strengthen the prompt instruction, a late-turn Stop-hook
> self-check, an effort bump) are aimed at the wrong target — they would make the agent write *more
> reliably to the same wrong place*. The fourth (structured output) sidesteps the path but re-plumbs
> where the gate reads the verdict, which violates the #314/ADR-0015 boundary the ticket forbids
> re-opening. A reframe is proposed in **Open Questions** for the user to decide at the Research
> Exit Gate.

Scope anchor (clarified intent): reduce how often the overnight review's `could_not_run` path fires,
without modifying the #314/ADR-0015 gate. Research was steered by verified context (the overnight
prompt is `cortex_command/pipeline/prompts/review.md`, it already carries CRITICAL/MUST write
instructions, the effort lever is model-gated on sonnet). That steer held — but the deeper
investigation found the firing is mechanical, not behavioral.

---

## Codebase Analysis

**The gate seam.** `dispatch_review()` (`cortex_command/pipeline/review_dispatch.py:142`) runs the
post-merge review. After `dispatch_task()` returns it calls `parse_verdict(review_md_path)` **only when
`result.success`** (`:292-293`); a missing/unparseable file resolves to the synthetic `_ERROR_RESULT`
sentinel (`parse_verdict`, `:89-100`) → the `could_not_run` path. The artifact path is computed at
`:208` as `review_md_path = lifecycle_base / feature / "review.md"`, with `lifecycle_base` defaulting to
the **relative** `Path("cortex/lifecycle")` (`:149`).

**The prompt.** `_load_review_prompt` (`:110-135`) substitutes only `{feature}`, `{spec_excerpt}`,
`{worktree_path}`, `{branch_name}` — **there is no absolute `review_md_path` placeholder**, so the
prompt's write target (`prompts/review.md:51`, `cortex/lifecycle/{feature}/review.md`) reaches the
agent as a **relative** path.

**DispatchResult** (`dispatch.py:319-341`) carries `success`, `output` (the concatenated assistant
text), `error_type`, `error_detail`, `cost_usd`, `diagnostics`. It does **not** carry `stop_reason`,
`num_turns`, `structured_output`, or `session_id` — the SDK parses all of these but the dispatch
discards them (logged-only at `:889-905`). Any structured-output or warm-resume mechanism would
require `DispatchResult` to grow those fields.

**Interactive vs overnight prompts already agree on the contract.** `skills/lifecycle/references/review.md`
(interactive, used by `report.py §4a`) and `cortex_command/pipeline/prompts/review.md` (overnight)
emit the **same** verdict JSON (`verdict` / `cycle` / `issues` / `requirements_drift`). The only
divergence is the interactive-only `## Suggested Requirements Update` prose (auto-applied when a human
is present). A worktree-mode-path fix on the overnight side therefore does **not** force a change to
the interactive prompt.

**Files a fix would touch:** `cortex_command/pipeline/review_dispatch.py` (`:149`, `:208`, `:293`,
`:563` — the path source and the two parse seams), `cortex_command/pipeline/prompts/review.md:51` (the
relative write target), and the `dispatch_review` call sites in `cortex_command/overnight/outcome_router.py`
(`:1114`, `:1521`, `:1831`). No L1/parity/size gate governs `prompts/review.md` (it is package-internal,
not a skill).

## Web Research

External consensus strongly favors the structural direction over prose. "LLM compliance with
instructions is probabilistic, not deterministic; prompt-based instructions must be combined with
deterministic outer-harness constraints (linters, CI gates, post-run verifiers)" — the HEAT-24 harness
verifies file-level outputs via **deterministic post-run workspace checks**, never trusting the agent's
claim (Augment Code "Harness Engineering"; agent-harness.ai). "Narration-instead-of-action" (the model
saying it did a thing instead of calling the tool) is a named anti-pattern (JetBrains). The
reflection / evaluator-reflect-refine loop with a bounded `max_iterations` is the standard
"agent-must-produce-a-valid-artifact" pattern (AWS Prescriptive Guidance).

Anthropic SDK/API affordances relevant to *forced final action* (all corroborated by the SDK-mechanics
angle below):
- **Agent SDK structured outputs** (`output_format` + JSON Schema): SDK validates the result and
  re-prompts internally, failing loud with `error_max_structured_output_retries`; the validated payload
  lands on `ResultMessage.structured_output`. Compatible with extended thinking. Carries the verdict as
  the **return value, not a file**. Docs: code.claude.com/docs/en/agent-sdk/structured-outputs.
- **`tool_choice` forced** (`any`/`tool`): structurally suppresses closing prose, but **incompatible
  with extended/adaptive thinking** (errors) — a hard conflict for Opus 4.7/4.8. Not exposed in this
  SDK's options path anyway.
- **`stop_reason` handling**: the docs explicitly say `end_turn` is *not* a reliable signal that a
  required action happened — pair it with a deterministic post-run file check and re-prompt in a new
  user turn. This is the harness-backstop pattern.
- **Effort**: lower effort → fewer tool calls; under-effort or `max_tokens` truncation are documented
  contributors to skipped final writes. Anthropic recommends starting at `xhigh` for agentic work with
  generous `max_tokens`. (Relevant to the ticket's effort question, but see the model-gating constraint
  and the actual root cause — effort is not the lever here.)

## Requirements & Constraints

- **#314 / ADR-0015 boundary (must NOT re-open).** The gate splits a genuine dispatch crash
  (`success == False` → revert + `review_dispatch_crash`) from a could-not-run review (`success == True`,
  no usable verdict → **preserve** the merge, `merge_reverted=False`, flag on morning report +
  integration-PR marker, systemic breaker under `review_no_artifact`). `parse_verdict(review_md_path)`
  **is** the gate seam. The positive `could_not_run` discriminator is what downstream routing keys on.
  (`cortex/requirements/pipeline.md` Post-Merge Review; `cortex/adr/0015-*.md`.)
- **MUST-escalation policy** (`CLAUDE.md`). A new MUST/CRITICAL needs an F-row/transcript evidence
  artifact; before escalating, run `effort=high` then `xhigh` and record the result; **if the dispatch
  path doesn't expose `effort` as a tunable for the case, cite the file and file a wiring ticket — do
  not escalate as a workaround.** The overnight prompt *already* uses CRITICAL/MUST language, so further
  prose-strengthening is the disfavored lever twice over (already present; and would need an effort-first
  evidence artifact the model-gating makes awkward to obtain).
- **Design principles.** "Prescribe What/Why, not How" and "structural separation over prose-only
  enforcement for sequential gates" (`CLAUDE.md`) both point at a structural fix over prompt prose.
- **Gates on the touched files.** No L1-surface ratchet, no SKILL parity mirror, no 500-line cap apply
  to `cortex_command/pipeline/prompts/review.md` or `review_dispatch.py` (package internals). The
  events-registry gate only bites if a new event name is introduced.

## Tradeoffs & Alternatives

This section evaluated the four *adherence-hardening* mechanisms before the root cause was pinned. With
the root cause known (path divergence), their standing changes — captured here and in Adversarial.

- **(A) Orchestrator-side post-dispatch verify + bounded retry** (reuse the `parse_verdict` seam).
  Feasible and consistent with existing convention (see Adjacency — fix/repair/recovery dispatches
  already use a SHA circuit breaker; implement verifies via `exit-report.exists()`). As an *adherence*
  fix it is the structural backstop the ticket half-anticipates. **But against the actual root cause it
  only helps if it checks the artifact at the path the agent actually wrote** (the absolute/worktree
  path) — a verify against the wrong (main) path detects nothing new.
- **(B) Structured output / forced `submit_verdict` tool.** `output_format` is the strongest *payload*
  guarantee, but it carries the verdict as a return value and **re-plumbs where the gate reads the
  verdict → crosses the #314 boundary** (see Adversarial). A forced tool call isn't available in this
  SDK options path and conflicts with extended thinking.
- **(C) Late-turn self-check in the prompt (Stop hook is the structural reading).** A Stop hook can
  block `end_turn` until `review.md` exists. As a generic adherence guard it is attractive — **but for
  this incident it is defeated by the same cwd ambiguity that caused the bug** (it runs in the agent's
  worktree cwd, stats the worktree path, finds the file, and never blocks). See Adversarial.
- **(D) Model/effort escalation.** Model-gated: the incident ran on **sonnet**, and
  `_MODEL_SUPPORTED_EFFORTS['sonnet']` excludes `xhigh` (`dispatch.py:188`); only `(complex,high|critical)`
  cells get `xhigh` and those route to **opus**. So "effort high→xhigh" is impossible on the sonnet
  review dispatch without a model escalation. And the failure was mechanical (wrong directory), not a
  reasoning-depth shortfall — escalation would change nothing. Per the MUST-escalation policy this should
  be **explicitly declined with rationale recorded**, and the effort-not-independently-tunable-for-review
  observation filed as a (separate, low-priority) wiring note rather than acted on here.

**Recommended approach (post-root-cause):** a **path-contract fix** — make the gate read where the agent
writes by resolving the review artifact path against a single, explicit, absolute source shared by writer
and reader. Optionally back it with a structural post-dispatch existence check at that *same resolved
absolute path* as a durable backstop for genuine future narration-instead-of-write. Decline B and D.

## SDK & Dispatch Mechanics

Installed SDK: `claude-agent-sdk>=0.1.46,<0.1.47`. `ClaudeAgentOptions` currently sets `model`,
`max_turns`, `max_budget_usd`, `cwd=str(worktree_path)` (`dispatch.py:792`), `permission_mode`,
`allowed_tools`, `system_prompt`, `env` (with `CORTEX_REPO_ROOT` overridden to the worktree at `:690`),
`settings`, `effort`, `stderr`, `cli_path`.

Exposed-but-unused enforcement-relevant fields (verified by introspecting the installed dataclass):
- **`output_format: dict | None`** → renders to `--json-schema`. Structured-output validate+re-prompt
  loop, fail-loud `error_max_structured_output_retries`. Verdict lands on `ResultMessage.structured_output`
  (currently discarded by `DispatchResult`).
- **`hooks: dict[HookEvent, list[HookMatcher]]`** including a **`Stop`** event. `decision:"block"` +
  `reason` "prevents Claude from stopping, continues the conversation" — re-prompts in-session. Needs a
  bounded re-block count and the *resolved absolute* target path (a bare relative path in the hook
  re-introduces the cwd ambiguity, per ADR-0009).
- **No `tool_choice` / forced-final-tool** field exists in this options path.
- **Same-session re-prompt is not possible on the current stateless `query()` path** ("Cannot interrupt
  or send follow-up messages"). A follow-up is a **cold fresh dispatch** unless switched to
  `ClaudeSDKClient` or `session_id` + `resume=`.

`effort` is passed through as a raw `--effort` flag, which is why `xhigh` works at the dispatch layer
even though the SDK's own `effort` Literal omits it — but the value is still rejected for non-opus models
by `resolve_effort` (`dispatch.py:282-288`).

## Failure-Mode / Root-Cause Analysis

**Primary root cause — CONFIRMED end-to-end (worktree-vs-main path divergence):**

- Agent side: `dispatch.py:792` sets `cwd=str(worktree_path)` (and `:690` sets
  `CORTEX_REPO_ROOT=worktree_path`); `prompts/review.md:51` gives a **relative** write target → the
  agent writes `review.md` **inside the worktree**.
- Gate side: `review_dispatch.py:208` builds `review_md_path` from the **relative** `lifecycle_base`
  default (`:149`); all three `dispatch_review` call sites in `outcome_router.py` (`:1114`, `:1521`,
  `:1831`) **omit `lifecycle_base`**; `parse_verdict` reads it against the **orchestrator's cwd**.
- Orchestrator cwd = **main repo**: `runner.py:1823` spawns the batch runner with **no `cwd=`**, so it
  inherits the launchd repo-root (main); the runner never `chdir`s. So writer-root (worktree) ≠
  reader-root (main).

**Incident artifacts (independently verified at `/Users/charlie.hall/Workspaces/wild-light/`):** the
worktree `review.md` exists, **untracked (`??`)**, 5181 bytes, a complete `APPROVED` verdict with proper
Stage-1 prose; the main-repo path is genuinely **empty**; `events.log` shows only `review_verdict ERROR
cycle 0`. Because the artifact was never committed, the post-merge state never carried it to the
integration branch either.

**Ruled out:** turn-budget exhaustion (the `is_error=True`/`error_max_turns` path returns
`success=False` → the *crash* branch, not `could_not_run`; the incident logged a normal
`dispatch_complete` and resolved `could_not_run=True`, only reachable with `is_error=False`).
Narration-instead-of-write (the worktree artifact exists and is valid). Reasoning-depth / model
shortfall (the agent reasoned and wrote correctly).

**Precision caveats (do not change the root cause):** the "17 of 30 turns" figure is **not independently
verifiable** from the captured artifacts and conflicts with the round-2 batch plan tiering occlusion
`simple` (`max_turns:20`); and the "Write succeeded in `agent-activity.jsonl`" evidence was **mis-sourced**
(that file, mtime 04:07:54, predates the 04:10:58 review write and contains the *implement/fix* agents,
not the review agent). The proof the review agent wrote is the worktree artifact itself, which is solid.

## Adjacency & Reuse

- **Strong existing precedent for orchestrator-side post-dispatch verification.** Commit-producing
  dispatches (fix, repair, integration-recovery) use a **SHA circuit breaker** (capture HEAD before/after,
  defer if unchanged); the implement/builder dispatch verifies via `exit-report.exists()` + an
  idempotency token in `pipeline-events.log`. The review path is the outlier that trusts
  `parse_verdict` without a "was the artifact produced *this run*, at the path I read?" check. A
  structural verify is therefore *idiomatic*, not novel.
- **The right absolute resolver already exists and is unused here.**
  `feature_executor._resolve_lifecycle_base()` (`:91`) returns an **absolute**
  `_resolve_user_project_root() / "cortex" / "lifecycle"`; `dispatch_review` ignores it and uses the
  relative default. `dispatch_review` already receives `worktree_path` as an argument.
- **Prompt sync:** overnight and interactive prompts already agree on the verdict-JSON contract; their
  one divergence is intentional. No forced sync.

## Adversarial Review

The adversarial pass verified the root cause against code *and* the incident artifacts and surfaced the
reconciliation every other angle missed, plus a new defect:

- **The real conditional (why the system "mostly works"):** classifying all `review_verdict` history by
  phase-transition signature, **only two features ever traversed the terse worktree-mode `dispatch_review`
  path** (`occlusion-field` → ERROR; `god-ray-look-redesign` → an APPROVED whose note is hand-written
  interactive prose, not a clean pipeline pass). The 31 other "APPROVED" reviews are trunk/interactive
  reviews where **agent cwd == gate cwd == main**, so no divergence occurs. The bug is therefore **not** a
  fleet-wide stale-read; it is a **near-universal failure of the rarely-exercised worktree-mode overnight
  review gate.** This is the correct framing of #319: not "the agent sometimes doesn't write," but "the
  worktree-mode overnight review gate reads the wrong directory ~always."
- **The path bug defeats the proposed adherence fixes.** A **Stop hook** registered on the review
  dispatch runs in the agent's session (cwd = worktree); it would stat the worktree path, **find the file
  present, and never block** — blind to the divergence. Prompt/effort hardening writes more reliably to
  the wrong place. **Structured output** sidesteps the path but moves the verdict source off-disk →
  **re-plumbs the #314 gate seam** (`parse_verdict`), and breaks the committed-`review.md` artifact
  contract read by `common.py:328`, `scan_lifecycle.py:161`, and the morning report → **off-limits per
  the ticket boundary.**
- **New defect, unflagged by any other angle (separate concern):** the incident's `feature_deferred`
  event carries `merge_reverted: true` **and** `could_not_run: true` **and** `review_dispatch_crashed:
  true` simultaneously. In the installed code these are mutually exclusive, and ADR-0015 says
  `could_not_run` **preserves** the merge (`merge_reverted=False`) — yet this event reverted it. Either
  the run executed a pre-ADR-0015 build (version-at-run is unverified) or the flag-coherence ADR-0015
  promised is broken. This is *not* #319's scope, but it bears on whether the incident's gate behavior
  matched its ADR and should be triaged separately.

## Open Questions

1. **[DECISION — for the user at the Research Exit Gate] Reframe #319?** The ticket's premise
   (artifact-write *adherence*) is falsified by the evidence; the verified root cause is a
   **worktree-vs-main path-contract divergence** in the worktree-mode overnight review gate. Recommended
   reframe: **"Fix the review-artifact path contract so the worktree-mode gate reads where the agent
   writes."** Proceeding as-written (adherence hardening) would ship a fix aimed at the wrong target.
   This is a scope change that the user should ratify before Spec.

2. **[DESIGN — for Spec] Which path-contract fix?** Two coherent options, with a real tradeoff:
   - **(1) Read from the worktree** — resolve `review_md_path` against the `worktree_path` the gate
     already receives. Smallest diff; matches the agent's actual behavior; stays entirely outside the
     #314 verdict-semantics gate (only changes *which directory the existing seam reads*). **Caveat:** the
     agent's `review.md` is untracked and lives only in the worktree, so the artifact is **not** persisted
     to the main-repo lifecycle dir that the morning report / `scan_lifecycle.py` / `common.py` read for
     the audit trail.
   - **(2) Anchor both sides to an absolute main-repo path** — substitute an absolute `{review_md_path}`
     into the prompt (the agent can write outside its cwd under bypassPermissions) and have the gate read
     that same absolute path (via the already-existing `_resolve_lifecycle_base()`). Larger blast radius
     (prompt + path plumbing) but lands the artifact where every downstream reader and the morning report
     expect it. A hybrid (read worktree for the gate **and** copy the artifact to main for persistence) is
     also viable.
   The artifact-persistence-for-the-morning-report requirement is the deciding factor and should be
   settled in the spec interview.

3. **[DESIGN — for Spec] Keep a structural verify as a durable backstop?** Independent of the path fix, a
   post-dispatch existence/parse check at the *resolved absolute* path (idiomatic per Adjacency's SHA
   circuit-breaker precedent) would catch genuine future narration-instead-of-write and would have made
   this incident fail loud immediately. Worth including as a small second layer, or defer as scope-creep?
   (A Stop hook is **not** recommended: cwd-blind to this bug and net-new SDK surface.)

4. **[DECLINE — record rationale] Effort/model escalation (ticket candidate D).** Decline: model-gated on
   sonnet (`xhigh` unsupported; `dispatch.py:188`) and the failure was mechanical, not reasoning-depth.
   Per the MUST-escalation policy, record the decline; optionally file a separate low-priority wiring note
   that the review dispatch doesn't expose an independent effort override.

5. **[TRIAGE SEPARATELY — not #319 scope] Flag-coherence defect.** The incident `feature_deferred` event
   asserts `merge_reverted` + `could_not_run` + `review_dispatch_crashed` together, contradicting
   ADR-0015's preserve semantics. Determine whether this is a pre-ADR-0015-version artifact or a live
   flag-emission bug, and file a separate ticket if the latter. This bears on whether the could-not-run
   path actually behaved per its ADR during the incident.
