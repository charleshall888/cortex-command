# Research: Give operator direction on an `escalated` lifecycle a recorded exit path

Five angles dispatched (complex + high). The core wave reached **contradictory recommendations** — prior art favored a real transition, the tradeoffs analysis favored typing the existing escape hatch — and the adversarial angle adjudicated on facts that the orchestrator then re-verified independently. The verification is recorded in `## Open Questions` Q1.

## Codebase

### The terminal flag is test-enforced, so Alternative A cannot avoid flipping it

`State.terminal` (`transition_table.py:82-96`) has three readers, all outside the table module:

- `describe.py:85,174` — flattens into the served payload and the generated `docs/lifecycle-transition-table.md` (CI-diffed against a fresh regeneration).
- `next_verb.py:279` — `_nominal_forward_path` stops at "the first terminal at/after the current state," which is what keeps branch terminals off the nominal line.
- `next_verb.py:343,354` — `reference = None if st.terminal else f"{state}.md"`, and the flag is echoed into `evidence_trace[0]`.

`_check_invariants()` (`transition_table.py:570-607`) asserts nothing about terminal-vs-outgoing. That guard lives in tests instead:

- `tests/test_transition_table.py:128-132` — `test_terminal_states_have_no_outgoing_edges`. **Adding any outgoing edge while `terminal=True` fails immediately.** The flip is forced, not optional.
- `tests/test_transition_table.py:94-115` — the converse: once non-terminal, `escalated` must have ≥1 outgoing edge or it is a stranded dead end.

Consequence of flipping: `next` serves `reference: "escalated.md"`, and **no such file exists** under `skills/build/references/` — so Alternative A also owes a new phase-reference doc authored under `docs/policies.md`'s phase rules. `_nominal_forward_path` from `escalated` would additionally run on to `cancelled`, since `STATES` order is `…complete, escalated, cancelled` (`transition_table.py:97-106`) and the walk no longer stops.

### #433's precedent is cheap for a reason that does not transfer

Commit `098a354e`. Diffstat: `implement_transition.py` (+52), `transition_table.py` (+22), the generated doc, `skills/build/references/implement.md` (+4) and its mirror, `size-pin.txt`, plus two test files (+442).

It needed **zero** changes to `advance.py` — no `_VERBS`, no `_VERB_TO_OWNING`, no `_build_parser`, no `main()` — because `implement-rework` was already owned by an existing B1 verb (`implement_transition`), and the CLI call site worked unchanged from either departure state. It also never touched `State.terminal`: `implement-rework` (`transition_table.py:101`) was declared `terminal=False` from the start and was an *accidental* dead end.

`escalated` is a **declared** terminal, and **no existing verb departs it**. So Alternative A needs a fifth B1 module wired into a hardcoded switch in six places:

| Place | File:line |
|---|---|
| `_VERBS` tuple | `advance.py:103` |
| `_VERB_TO_OWNING` | `advance.py:107-112` |
| `KNOWN_STATES` union | `advance.py:178-186` |
| `_emission_plan()` branch | `advance.py:371-525` |
| `_build_parser()` subparser | `advance.py:1156-1247` |
| `main()` dispatch | `advance.py:1258-1290` |

Plus `_PAUSE_OWNING_VERBS` / `_PAUSE_TYPED_RESUMES` (`advance.py:130-147`) if it gates on a pause — omitting an entry makes the typed resume get refused by the very pause it exists to clear (the #400 circularity, documented at `advance.py:136-143`). And `tests/test_transition_table.py:31-36`'s `B1_VERBS` dict is hand-maintained: a new module must be added there or `test_no_transition_row_without_a_real_b1_arm` flags the new row as an orphan.

### Idempotent replay is `advance.py`-only machinery

`advance()` short-circuits with `replay: "already-emitted"` (`advance.py:1026-1031`) when every planned emission is already present, via `_row_present(rows, event, match)` — a parsed-field match, never a substring probe. Match dicts are arm-specific: review-verdict keys on `{"cycle": cycle}` (`:437`), batch dispatch on `{"batch": batch}` (`:488`).

The **#424 fix** is the directly relevant precedent: `implement-transition`'s `phase_transition` match now keys on `{"from": departed, "to": route}` using the *resolved* departure (`:508`), not the literal `"implement"`. The comment at `:500-504` names the bug — keying on the literal made cycle 1's genuine implement→review row satisfy the rework→review probe, so the second transition was swallowed as a replay and the feature stalled.

`lifecycle_event.log_event` / `log_event_at` (`lifecycle_event.py:127-173`) **never dedupes** — the module docstring states there is no read-modify-write step. All writers share one flock discipline via `_append_event_atomic`, but replay protection is not shared.

### Alternative B mechanics

`cortex-lifecycle-event log --event <name>` accepts **any** string — `metavar="NAME"`, no `choices=`. There is no event-name registry: the registry file is gone and `project.md:41` lists "events-registry gate and stale-deprecation audit (+ registry file)" among gates retired without named evidence. ADR-0020 still narrates its original purpose; the enforcement is gone.

The remaining registration surface is `_EVENT_SUBCOMMANDS` (`lifecycle_event.py:257-329`), auto-wired into `_build_parser()`. Adding a typed subcommand there is genuinely small — one dict entry, no dispatch rewrite. But it inherits **no** dedupe, **no** from-state gate, **no** pause scoping, and **no** status-projection seam; those are all `advance()`-body-only (`:1035-1131`).

### Alternative C mechanics

`wontfix_cli.py` is a three-step, order-enforcing, fail-forward sequence: `_archive_move` (`:80-97`) physically moves `cortex/lifecycle/<slug>` → `archive/<slug>`; `_append_wontfix_row` (`:118-129`) hardcodes `event: "feature_wontfix"`; `_terminalize_backlog` (`:132-162`) hardcodes `--status wontfix --lifecycle-phase wontfix`. It is entirely outside the transition table (zero `wontfix` matches in `transition_table.py`) and has no from-state gate. It can serve a genuine "cancel," but cannot serve `escalated → complete` without breaking its contract for existing callers.

### Full surface inventory (minimal one-edge version of A)

`transition_table.py` (flag + row) · a new `escalation_resolve.py` B1 module · `advance.py` ×6 · `tests/test_transition_table.py`'s `B1_VERBS` · a new test file mirroring `test_implement_rework_exit.py` · `resolve.py:86` and `phase_labels.py:73-74` (both hardcode REJECTED prose) · `hooks/cortex-scan-lifecycle.sh` (bash mirror, pinned by `tests/test_lifecycle_phase_parity.py`) · `docs/lifecycle-transition-table.md` regen · `skills/build/references/review.md:55` + `skills/build/SKILL.md` + `size-pin.txt` · a new `skills/build/references/escalated.md`.

No `plugins/cortex-core` mirror exists for `cortex_command/` package files — those are outside the dual-source set. The skill prose edits do carry mirrors, auto-rebuilt by pre-commit.

## Web

Surveyed Temporal, AWS Step Functions, Netflix Conductor, Argo Workflows, Airflow, GitHub Actions environments, BPMN/Camunda, and SCXML/Harel statecharts.

**Every mature engine models human override as a transition on the same machine, triggered by an external signal** — never as an out-of-band log write. Temporal parks the workflow and resumes on a Signal recorded in its own Event History. Step Functions' `.waitForTaskToken` pauses the machine and resumes only on a matching token. Conductor has first-class `HUMAN`/`WAIT` task types. Argo's `retry`/`resume` are gated verbs restricted to specific prior states. GitHub environment approvals make the job sit in a non-terminal `pending` status with Approve/Reject as native, natively-recorded actions.

**"Terminal state a human can leave" is a recognized modeling smell.** SCXML/Harel treat a `<final>` state as meaning its *parent* region is done; BPMN draws a hard line between an end event (truly terminal, no outgoing flow) and an intermediate/boundary catch event (non-terminal, resumes normal flow). The standard fix across all of them is a dedicated non-terminal `awaiting-input` / `suspended` / `pending-review` state — not a privileged writer permitted to violate terminality.

**BPMN escalation is the closest structural analogue.** Fetched from Camunda 8 docs: an escalation is *thrown* with an `escalationCode` and *caught* by a boundary event or event subprocess; it is explicitly "non-critical" — unlike an error, it does not abort the process, and after the catch handles it **execution proceeds normally**. Whether the escalation record survives is left to the engine's history layer, not the control-flow spec — consistent with "the override is additive, recorded at the audit layer."

**Idempotency prior art**: client-generated idempotency key on the *command*, checked atomically with the append; `causationId`/`correlationId` as standard metadata. For a human override the natural key is *which escalation episode is being resolved* — `(aggregate_id, escalation_instance_id)` — not wall-clock time.

**Override audit requirements**: corrections are appended as compensating events, never rewrites ("the original event remains in the stream"). Break-glass/SOX practice requires who, when, why (mandatory reason), and a reference to what was overridden, plus alerting on use. Four-eyes/maker-checker literature names the rubber-stamp failure mode, and its structural defense is a mandatory justification field plus segregation of duties — not a state-machine control.

**Anti-patterns**: no surveyed system uses "generic log-an-arbitrary-event" as its human-override mechanism; it appears nowhere as sanctioned practice, and is consistently what these systems built *away from*. Unscoped "admin can force any transition" is tolerated only wrapped in break-glass controls.

Angle's verdict: (A) is what the prior art supports; (B) is "a compromise, not a pattern with direct prior art"; (C) is "actively contraindicated" because BPMN goes out of its way to distinguish escalation-resolution (returns to live flow) from termination.

*Sourcing note*: the Camunda escalation-events page was fetched directly and was the most useful primary source. Two Temporal fetches returned thin content; the remaining findings are search-result summaries, flagged as such by the angle.

## Requirements & Constraints

### `cortex/requirements/project.md`

- **`:49` Served lifecycle verb class** — `next`/`advance`/`describe` "own the closed, wheel-owned transition table (config selects parameters only — it can never introduce a state or edge)." A resolution arm must live in one of those verbs or justify a fresh ADR-0019 exception.
- **`:23` Deletion bias** — machinery must name measured cost or observed failure, not a hypothetical. Bears directly on the zero-occurrence decisions.
- **`:25` Solution horizon** — if a reuse option is already known to need redoing, the durable version is required, not a documented deferral.
- **`:41` Enforcement gates** — the reference-size ratchet and dual-source mirror reconciliation both fire on the skill prose edits.
- **`:31` Kept pauses** — a new pause needs marker + `kept-pauses-data.toml` row + `just kept-pauses` regen + parity test. No `escalat*` row exists today.
- **`:46` Wheel-binstub vs working-tree** — `cortex-*` binstubs run the installed wheel; verify in-progress table changes via `python3 -m` or `CORTEX_COMMAND_FORCE_SOURCE=1`.
- **`:73-92` Scope** — "AI workflow orchestration (skills, lifecycle, pipeline)" is In Scope; nothing in Out-of-Scope or Deferred touches this.

### ADRs

- **ADR-0024** (`:23`) — the closed-table clause quoted above; also (`:31-34`) legacy typed verbs retire only via an operator-decided protocol-floor bump.
- **ADR-0025** (`:20`) — "events.log is the authoritative phase source wherever machine rows exist." Today's hand-append is exactly the drift this exists to close.
- **ADR-0016** (`:20-21`) — backlog CLIs gain no backend awareness; any status write-back stays backend-blind.
- **ADR-0019** (`:17`) — the dumb-arg-actor rule ADR-0024 is a bounded carve-out from.
- No ADR names `escalated`, `sanctioned_override`, or `wontfix`. These live only in docstrings and backlog tickets.

**ADR three-criteria gate applied** (`cortex/adr/README.md:23-25`): hard-to-reverse **clears** (the table is append-only/reserve-on-deprecate — a shipped transition id can never be reused); surprising-without-context **plausibly clears**; real-trade-off **clears** (three credible alternatives). **Verdict: this decision is ADR-shaped**, particularly because ADR-0024 itself was framed as a decision "recorded rather than an unmarked extension."

### The transition table's own contract (`transition_table.py` docstring)

- `:12-22` — "No consumer config can add a state or reorder an edge… A config key that names no parameter has zero effect on the table." The edge must land as code.
- `:24-27` — append-only, reserve-on-deprecate, with import-time invariant checks.
- `:29-33` — completeness: "every B1 verb decision arm maps to exactly one transition row," derived by importing the real B1 modules.
- `:36-38` — data + pure accessors only, no I/O.

### Protocol

`protocol.py:24-27` — "`PROTOCOL_VERSION` is append-only: bump it… when a payload change is not backward-compatible for the prose… A bump that would strand out-of-repo consumers is a protocol-floor decision made deliberately by the operator." Currently `3`. Its changelog shows precedent for bumping when `next`/`advance` gain a **new returnable state** (v2: `approved-direct`; v3: `enter_command`). Not an automatic trigger — a judgment call the operator owns.

### Ratchet sequencing

`skills/build/references/size-pin.txt` is pinned at **57964** bytes with two prior annotated `# raised:` exceptions — `lifecycle-id=433` ("the prescribed rework loop was previously unrepresentable in the state machine") and `lifecycle-id=449`. Edits need ratchet-refs → build-plugin → ratchet-refs, with the pin staged by hand.

## Tradeoffs & Alternatives

*This angle's recommendation was overturned by the adversarial angle on verified facts. Its decision-set analysis stands; its architectural recommendation does not. Both are recorded.*

### Decision set (this analysis survives)

| Decision | Observed evidence | Already served? |
|---|---|---|
| Proceed to Complete | The one occurrence (2026-08-05) | No |
| Cancel | None | Arguably by `wontfix` — but see Adversarial §5 |
| Return to Implement | None | No |
| Return to Plan/Spec | None | No |

A real tension worth surfacing: `skills/build/references/review.md:37` already tells a REJECTED verdict to "escalate immediately, **recommending a return to plan or spec**" — the skill's stated intent leans *backward*, while the only operational evidence points *forward*. Under the Deletion-bias bar, zero-occurrence decisions do not clear today.

### Terminal-flag blast radius (this analysis survives and is important)

Beyond `State.terminal`'s three readers, **two independent hardcoded registries treat `escalated` as terminal without consulting the flag at all**:

- `common.py:533` — `_EVENTS_TERMINAL_STATES = frozenset({"complete", "escalated", "cancelled"})`, consumed at `:368,623` to decide whether the `-paused` suffix applies.
- `hooks/scan_lifecycle.py:195-198` — `_is_terminal_mismatch` checks `events_phase in ("complete", "escalated")`.

Flipping the table flag does nothing to either. "Terminal" is not one property in this codebase — it is the flag plus two string sets.

### The overturned recommendation

The angle recommended (B) — a typed `escalation-resolve` subcommand in `_EVENT_SUBCOMMANDS`, routed via `common.py:507`'s `_TERMINAL_EVENT_TO_STATE` as `"escalation_resolved": "complete"` — on the argument that `relayed-consent` is the pause kind overnight answers *unattended*, so putting a resolve arm in `next`'s served `outgoing` would invite an overnight loop to auto-close escalations, while a `cortex-lifecycle-event` subcommand is invisible to the served loop by construction.

**Both halves of that argument are factually wrong.** See Adversarial §1 and §2.

## Adversarial

### The overnight argument for (B) is inverted at three levels

**(a) The unattended runner cannot reach `escalated` at all.** `pipeline/review_dispatch.py:441-455` handles REJECTED at any cycle by writing a deferral file and *deliberately emitting no transition row*. Its own comment: "Routing REJECTED through the advance review-verdict body would emit a phase_transition review→escalated… To preserve the projection, no transition-vocabulary row is emitted; the deferral is the record." `:684-696` does the same for cycle-2 non-APPROVED. **The overnight pipeline parks the feature at `review` plus a deferral — the autonomous loop (B) protects against is structurally incapable of occupying `escalated`.**

**(b) Overnight invokes arms by name from Python, not by reading `outgoing`.** `overnight/advance_lifecycle.py:304-310` calls `advance(verb="review-verdict", verdict="APPROVED", …)` directly. So "not in the served envelope" buys nothing — the runner does not consult `outgoing` to decide what to call, and could invoke a `cortex-lifecycle-event` subcommand just as easily. **(B)'s safety rests on the model not noticing a documented command.**

**(c) `relayed-consent` means the opposite of what the tradeoffs angle read.** `common.py:840-847`: *"Ordered most- to least-restrictive by resume authority: `relayed-consent` requires an operator resume, so it is the fail-closed default for an under-specified pause row."* `MOST_RESTRICTIVE_PAUSE_KIND = "relayed-consent"`. `advance.py:118`: `_ENFORCED_PAUSE_KINDS = frozenset({"relayed-consent", "phase-exit-wait"})` — one of exactly two kinds `advance` **structurally refuses to cross** (`_pause_refusal`, `:307-345`), while `question`/`config-conditional` are describe-only. It is the machine's strongest gate, not its weakest.

**(d) The human-only-edge affordance already exists.** A pause-hold arm at `escalated` carrying `PauseSpec(kind="relayed-consent")` renders into `pause_spec.specs` (`next_verb.py:329-337`) and makes any crossing advance refuse. `pause_kind` comes from the raw-row reducer (`next_verb.py:313`), not `resolve_lifecycle_phase`, so the terminal-state pause suppression at `common.py:623` does not hide it.

### (B) is the option that hands the escalation to an autonomous loop

`hooks/cortex-lifecycle-continue.sh` is the live Stop hook. Line 68: `case "$STATE" in review | complete) ;; *) exit 0 ;; esac` — **`escalated` exits 0 today; nothing pushes an escalated lifecycle.** Line 51 exits only if `feature_complete` is already present; line 74 exits only if `pause_spec.active`.

Run (B) through it: `escalation_resolved` → `_TERMINAL_EVENT_TO_STATE` → served state `complete`, with no `feature_complete` row and no pause spec. Line 51 passes. Line 68 matches. Line 74 passes. The hook fires its "crosses without operator confirmation… Do not ask whether to proceed" nudge.

**(B), sold as invisible to autonomous loops, routes a resolved escalation straight into an unattended Complete phase** — which per ADR-0004 means PR creation and a merge anchor. (A) with a `relayed-consent` hold would have been *refused*.

### (B) creates a fourth phase-truth reader

`_TERMINAL_EVENT_TO_STATE` has two consumers (`common.py:576`, `advance.py:219`). Four other readers derive completion independently:

| Reader | Mechanism | Result under (B) |
|---|---|---|
| `pipeline/metrics.py:230-238` | `feature_complete` OR `phase_transition to=="complete"` | returns `None` — "in progress" forever |
| `dashboard/data.py:336-343` | timeline built only from `phase_transition` rows | page says complete, timeline ends at escalated |
| `claude/statusline.sh:422-431` | greps `feature_complete`, then `feature_wontfix`, else review.md verdict | **pinned at "Escalated ⚠️" permanently** |
| `hooks/scan_lifecycle.py:196` | hardcoded tuple | unchanged either way |

`tests/test_lifecycle_phase_parity.py:604-634` carries three `feature_wontfix` parity tests, so the real cost of a new map entry is: the map, the bash ladder, three parity tests, metrics, and the dashboard. **(B)'s "no `transition_table.py` change, no `advance.py` change" omits the entire parity surface.**

The structural indictment: `_MACHINE_STATE_NAMES` (`common.py:521-531`) is explicitly *"pinned equal to the table by the resolver tests (drift tripwire)."* `_TERMINAL_EVENT_TO_STATE` has **no such pin**, so `tests/test_transition_table.py` cannot see a phase change routed through it. ADR-0024 says config "can never introduce a state or edge"; (B) introduces the edge `escalated → complete` from a module the table has never heard of. **The invisibility is the defect, not the feature.** And `feature_wontfix` already has all these holes today — (B) proposes to replicate a known-broken pattern and cite it as precedent.

### "Duplicates are benign" survives narrowly; the idempotency claim does not

The phase reducer is genuinely last-row-wins (`common.py:571-587`). Count-based readers exist (`common.py:314-355` counts `review_verdict` for cycle; `metrics.py:317-318`) but neither counts a new name. So the narrow claim holds.

But `log_event` never dedupes (`_append_event_atomic`, `lifecycle_event.py:76-115`, is a bare append), and replay protection is `advance.py`-only (`:150-166`). A re-run under (B) appends a second `escalation_resolved` **and** a second backlog write-back — violating the ticket's own Edge that idempotent replay "matters more here than elsewhere." Importing `advance`'s replay machinery into the escape-hatch verb makes it a worse-located (A).

### Cancel-via-`wontfix` erases the escalation

`wontfix_cli.py:6-11` archive-moves the lifecycle dir, and its own docstring cites the name-based archive-skip at `scan_lifecycle.py:907`. After archiving: the SessionStart scan drops it, `cortex-lifecycle-next <slug>` cannot resolve it, and the "Action needed: review returned REJECTED" hint (`scan_lifecycle.py:158-162`) vanishes. **Archiving is the most erasing action available — a direct violation of the ticket's Edge that "the resolution must not erase the escalation."** Compounding it, `_TERMINAL_EVENT_TO_STATE["feature_wontfix"] = "complete"`, so abandoning a REJECTED feature reports it as *complete*.

### The evidenced floor is mis-measured

`complete_route.py:34-48` routes on live git/gh state: `first_run`→step1, `on_main`→step9, `already_complete`→step12, `merged_*`→terminal. It does not care how you arrived. So landing in `complete` from `escalated` **does not skip Complete's work — it enters it**, and per §2 the Stop hook drives that entry unattended. The observed case (fixes committed outside the loop, on trunk) is the `on_main` route → step 9 onward, which still wants a PR and a merge anchor.

The 2026-08-05 occurrence does not evidence an edge to `complete`; it evidences an operator saying *stop*. Someone must decide whether resolve hands off to Complete's machinery or short-circuits it with `feature_complete` — "add one edge" does not encode that answer.

### The assumption nobody questioned: one state, two intents

`review_verdict._route_target` (`:152-163`) collapses REJECTED-any-cycle and CHANGES_REQUESTED-cycle≥2 into `escalated`; `_TARGET_TO_STATE` (`:166-170`) collapses them again. The arm identity `(review_verdict, "escalated")` **cannot distinguish them**. Every downstream surface then hardcodes the REJECTED story — `resolve.py:86-88`, `phase_labels.py:74`, `scan_lifecycle.py:158-162`.

**The 2026-08-05 provenance case was a cycle-2 CHANGES_REQUESTED.** Every surface the operator saw was lying about why the lifecycle stopped. That mislabel is a real shipped defect neither (A) nor (B) touches.

The two intents want different targets: a rework-cap exhaustion wants `implement-rework`; a reviewer's REJECTED wants plan/spec/cancel. Splitting them does not dissolve the terminal problem, but it dissolves the *hard half*: `rework-capped → implement-rework` is a **non-terminal edge, on an existing owning verb, to an existing state** — no terminal flip, no missing `escalated.md`, no fifth B1 module, no `B1_VERBS` entry, no `_EVENTS_TERMINAL_STATES` divergence — and it covers the actual intent of the sole observed occurrence.

### Other things that will bite

- **`advance` currently teaches the workaround.** `_SANCTIONED_OVERRIDE` (`advance.py:105-108`) makes every refusal point at `cortex-lifecycle-event log --event <name>…`. Whatever ships must re-point that string, or the machine keeps recommending the thing being removed.
- **Prose/topology disagreement under (A).** `_terminal_directive` (`next_verb.py:198-208`) falls through to `resolve._ROUTE_NEXT["escalated"]`; a non-terminal `escalated` still serves "ask the user for direction" unless both change together.
- **Protocol hygiene favors (A).** (A) changes `next`'s returnable shape (non-empty `outgoing`, non-null `reference`) — bump precedent exists. (B) changes the set of states a feature can occupy *without* a protocol change, so a stale plugin receives a `complete` it cannot explain and **no skew signal fires**.
- **Pre-existing wart**: `scan_lifecycle._is_terminal_mismatch` (`:186-201`) treats `escalated` as terminal, so every escalated feature whose backlog status is `in_progress` fires a permanent terminal-mismatch warning today.
- **The size-pin recurrence is itself evidence.** `size-pin.txt`'s two raised exceptions are lifecycle 433 ("the prescribed rework loop was previously unrepresentable in the state machine") and 449 (review.md and the gate table disagreeing). This ticket is the **third instance of the same pattern** — prose describing a transition the table cannot represent. That recurrence argues the fix belongs *in* the table.

## Open Questions

**Q1 — (A) vs (B): RESOLVED against (B).** The two angles contradicted each other, so the orchestrator independently re-verified all four load-bearing facts:

- `review_dispatch.py:441-455` confirmed — REJECTED writes a deferral and emits no transition row; overnight parks at `review`. (B)'s threat model cannot occur.
- `hooks/cortex-lifecycle-continue.sh:68` confirmed — `case "$STATE" in review | complete)`; `escalated` exits 0, `complete` autocontinues, and the line-51 guard passes when no `feature_complete` row exists. (B) therefore *creates* the unattended path it claims to avoid.
- `common.py:847` + `advance.py:118` confirmed — `relayed-consent` is `MOST_RESTRICTIVE_PAUSE_KIND` and is one of two kinds `advance` structurally refuses to cross. The tradeoffs angle had it exactly backwards.
- `common.py:507-531` confirmed — `_TERMINAL_EVENT_TO_STATE` has two consumers and, unlike `_MACHINE_STATE_NAMES` ("pinned equal to the table by the resolver tests (drift tripwire)"), carries **no** pin.

(B) is rejected. (C) is rejected on the ticket's own non-erasure Edge. Prior art, the codebase's own pause machinery, and protocol hygiene all point the same way: a gated transition on the machine.

**Q2 — Is the scoped floor the right floor? DEFERRED to Spec — the operator owns this.** The operator's scoping decision was "research decides the design; the one evidenced edge (`escalated → complete`) is the guaranteed floor." Research finds the floor is **mis-measured**: the 2026-08-05 occurrence was a cycle-2 CHANGES_REQUESTED (a rework-cap exhaustion), not a REJECTED, and `escalated → complete` *enters* the Complete phase rather than closing it out. The adversarial angle's cheaper alternative — split the two intents and give the rework-cap case a non-terminal edge back to `implement-rework` on the existing `review_verdict` verb — targets the observed evidence more precisely and avoids the entire terminal-flip cost. This contradicts the stated floor, so Spec must put it to the operator rather than resolve it silently.

**Q3 — Does resolve hand off to Complete's machinery, or short-circuit it? OPEN for Spec.** `complete_route.py` routes on live git/gh state and does not care how the state was reached. Landing in `complete` means entering the phase (PR creation, merge anchor per ADR-0004). If the operator's intent is "stop, this is done," that wants a `feature_complete` short-circuit instead. The two produce different targets and different emissions.

**Q4 — Does this decision get its own ADR? OPEN for Spec.** The three-criteria gate clears (`cortex/adr/README.md:23-25`), and ADR-0024 set the precedent of recording a table-contract decision "rather than an unmarked extension."

**Q5 — Protocol-floor bump? OPEN for Spec, operator-decided.** `protocol.py:24-27` frames it as bump-when-not-backward-compatible, an operator decision. Precedent exists for bumping when `next`/`advance` gain a new returnable state (v2, v3).

**Q6 — `_TERMINAL_EVENT_TO_STATE` has no drift tripwire. DEFERRED — separate ticket.** `_MACHINE_STATE_NAMES` is pinned equal to the table; the terminal-event map is not, so a phase change routed through it is invisible to `tests/test_transition_table.py`. This is a live gap independent of which option ships (it already affects `feature_wontfix`), so it should be filed rather than folded in.

**Q7 — The REJECTED mislabel is a shipped defect. DEFERRED to Spec for an in-or-out call.** `resolve.py:86-88`, `phase_labels.py:74`, and `scan_lifecycle.py:158-162` all tell an operator that a cycle-2 CHANGES_REQUESTED escalation is a REJECTED one. The 2026-08-05 operator saw all three. It is arguably in scope (Q2's split would fix it structurally) or arguably its own bug ticket; Spec decides.

**Q8 — `_SANCTIONED_OVERRIDE` must be re-pointed by whatever ships. RESOLVED — in scope.** `advance.py:105-108` currently instructs operators to hand-append, which is the practice this ticket removes. No option is complete while the refusal message still teaches it.

**Q9 — Two unrelated defects found incidentally. DEFERRED — file separately.** (a) `project.md:59` cites "→ ADR-0029" for "Lifecycle identity is the canonical slug," but `cortex/adr/0029-*.md` is about sync-allowlist conflict resolution; no ADR matches that content. (b) `scan_lifecycle._is_terminal_mismatch` fires a permanent terminal-mismatch warning for every escalated feature at backlog status `in_progress`.
