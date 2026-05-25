# Research: Reconcile SessionStart additionalContext lifecycle-summary block

> Scope anchor (from Clarify §5): make the SessionStart additionalContext lifecycle-summary block derive each incomplete-lifecycle entry's phase from on-disk truth (events.log) and cross-check against backlog frontmatter `status:`, surfacing disagreements explicitly so operator decisions are made on accurate state.

## Codebase Analysis

### Files in scope

- **Primary generator**: `cortex_command/hooks/scan_lifecycle.py`
  - `_build_additional_context()` (lines 345-457) — assembles the context string, including the active-feature header and the "Other incomplete lifecycles" enumeration.
  - `main()` (lines 460-800) — SessionStart entry; reads stdin envelope, scans `cortex/lifecycle/`, runs `detect_lifecycle_phase` per candidate (line 662), builds `incomplete: list[tuple[str, str]]` of (feature, encoded_phase) pairs, calls `_build_additional_context`, emits JSON to stdout.
  - `_encode_phase(phase, checked, total, cycle)` (line 681) and `_phase_label()` (lines 77-129) — render the per-entry phase string. Output forms include `"Implement (3/5 tasks done)"`, `"Implement — rework (review cycle 1)"`, `"Complete (awaiting merge)"`, etc.
  - `_interrupted_hint()` (line 132) — phase-specific resume hint text that the active-feature header consumes.
  - Stale-lifecycle filter (lines 633-656) — currently excludes features whose last events.log activity is >30 days old (or whose lifecycle dir is missing events.log + matches other heuristics).
- **Canonical phase detector**: `cortex_command/common.py`
  - `detect_lifecycle_phase()` public wrapper (lines 405-446) — caches via stat keys; exposed as the CLI subcommand `cortex-common detect-phase` referenced in `skills/lifecycle/SKILL.md` Step 2.
  - `_detect_lifecycle_phase_inner()` (lines 223-402) — the precedence ladder.
  - `TERMINAL_STATUSES` frozenset (lines 162-171) — `{complete, abandoned, done, resolved, wontfix, won't-do, wont-do, superseded}`.
- **Backlog status reader**: `cortex_command/backlog/ready.py:81` — `_STATUS_LINE_RE = re.compile(r"^status:\s*(.+?)\s*$", re.MULTILINE)` is the canonical frontmatter `status:` extractor used across the codebase.
- **Backlog slug→file resolvers (drift risk)**:
  - `cortex_command/overnight/outcome_router.py:_find_backlog_item_path` (used by overnight runner)
  - `cortex_command/backlog/resolve_item.py` (used by `cortex-resolve-backlog-item` CLI)
  - `cortex_command/dashboard/data.py:parse_backlog_titles` (slugified-title only; ignores `lifecycle_slug` frontmatter)
  - `cortex/backlog/index.json` — already keys backlog items by `lifecycle_slug` and can serve as a lookup map.
  - Ticket #254 tracks unifying these resolvers.
- **Overnight→backlog status mapping**: `cortex_command/overnight/outcome_router.py:326-377` — `_OVERNIGHT_TO_BACKLOG` maps `paused → in_progress`, `implementing → in_progress`, etc. This is steady-state behavior, not transient.
- **Peer observability surfaces (all call `detect_lifecycle_phase`; none cross-check backlog status)**:
  - `claude/statusline.sh` (renders the same encoded phase strings; lines 580-604; structural-exception comment at 376-454 explains why bash mirrors Python).
  - `cortex_command/dashboard/data.py` (imports `detect_lifecycle_phase` directly).
  - `cortex_command/overnight/cli_handler.handle_status` (reads events.log + overnight-state.json).

### Existing precedence ladder (in `_detect_lifecycle_phase_inner`)

1. `feature_wontfix` event present → `"complete"` (terminal, per `wontfix.md`)
2. `feature_complete` event present → `"complete"`
3. `review.md` verdict: APPROVED → `"complete"`; CHANGES_REQUESTED → `"implement-rework"`; REJECTED → `"escalated"`
4. `plan.md` task tally (gated by `plan_approved` / `plan_transitioned_out` events): all `[x]` → `"review"`; otherwise `"implement"`
5. `spec.md` exists (gated by `spec_approved` / `spec_transitioned_out`) → `"plan"` or `"specify"`
6. `research.md` exists → `"specify"`
7. default → `"research"`

**Gaps the ticket's motivating evidence depends on**: the ladder does NOT have rungs for `feature_paused` (the #209 case — last event was a pause, but the ladder returned `implement` or `review` from rung 4 based on plan.md task tally). The "events-log truth" framing in the ticket is therefore aspirational — the existing detector is mostly artifact-presence inference, with only one events.log rung (`feature_complete`) above the artifact checks.

### Integration patterns to follow

- **Backlog frontmatter parse**: reuse the `_STATUS_LINE_RE` pattern from `backlog/ready.py:81` rather than re-implementing.
- **Events-log read**: single-file, line-oriented JSONL; producers SHOULD include `schema_version` but readers MUST tolerate its absence as v1 (per `bin/.events-registry.md` and the historical-compat shim doctrine in `project.md`).
- **No new event types**: this work reads existing data only; surfaces mismatches in text. No registry entry needed.
- **Lazy-imports pattern**: scan_lifecycle.py:541-551 inlines expensive imports for cold-start performance; the reconciler must follow the same discipline.

## Web Research

### Claude Code SessionStart hook (authoritative behavior)

- Envelope shape: `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}`.
- **10,000-character cap** on `additionalContext` — over-cap output is silently replaced with a file-pointer preview. Mismatch annotations that push past this cap defeat the very signal #259 is adding.
- **No idempotency guarantee**: runs on every session start AND on `--resume`/`--continue` (with `source: "resume"`). Output is concatenated when multiple hooks match. The user sees the same mismatch block on every `/clear` and every resume in the same session — risk of operator training-to-ignore.
- **Performance-critical**: hooks block session setup; only `command` and `mcp_tool` types are supported.

### Reconciliation precedent in dev tooling (named drift, not silent reconciliation)

- **Terraform** — `plan -refresh-only` and `-detailed-exitcode` return exit `2` specifically when drift is present. Drift is named; reconciliation is an explicit operator command. Not silent.
- **Kubernetes** — controller `status` subfield exposes `Ready`/`Progressing`/`Degraded` conditions. Divergence between spec (desired) and status (actual) is the surface area; the API never collapses to a single value.
- **`git status`** — distinct markers (`??`, `M`, `A`, `D`) per divergence type. Each kind of mismatch is distinguishable.
- **Jujutsu (jj)** — flags working copy as "stale" when another workspace moved the working-copy commit; offers `jj workspace update-stale` as an explicit reconciliation command. The staleness is named in the UI.

### Event-sourcing / CQRS precedent

- Canonical guidance: events are source of truth; projections are caches that can be rebuilt by replay. But backlog `status:` is human-editable too, so it is a hybrid declarative+derived field — pure projection-replay would discard human intent (e.g., operator marking `wontfix` before events catch up). Argues against "events always win, silently overwrite frontmatter".

### Anti-patterns

1. **Silent preference** — picking one source and hiding the other is the failure mode #259 is fixing.
2. **Auto-correction without operator visibility** — rewriting one side from the other (without a visible mismatch annotation) reproduces the state-diff "mirrored state silently breaks" failure mode.
3. **Pure projection rebuild for a hybrid source** — treating backlog `status:` as a derived cache discards human-authored intent.
4. **Performance regression in SessionStart** — O(N×M) reconciliation on a hook that blocks session setup is a foot-gun.
5. **Over-cap silent truncation** — the 10K cap silently swaps the entire `additionalContext` for a file-pointer preview, vanishing the mismatch signal precisely when most needed.

## Requirements & Constraints

### From `observability.md`

- Statusline functional requirements (lines 15-25) require "active lifecycle feature name and phase match `events.log`" and `<500ms` invocation budget.
- No-writes constraint (line 93): observability subsystems are read-only with respect to session state files.
- **Critical gap**: `observability.md` does NOT define explicit acceptance criteria or latency budget for the SessionStart `additionalContext` surface itself — only for the statusline and dashboard. The spec phase needs to decide whether to inherit the statusline budget by analogy or define one.

### From `project.md` and ADRs

- **ADR-0001 (file-based state)**: chosen for reviewability — silent reconciliation defeats this goal.
- **ADR-0004 (multi-step Complete)**: events.log is canonical for phase transitions; `feature_complete.merge_anchor` field distinguishes "review" vs "merge".
- **TERMINAL_STATUSES (project.md:36-37)**: canonical terminal set lives in `cortex_command/common.py`; mirrored in `overnight/plan.py`; the frozenset in `overnight/backlog.py` is known divergence tracked separately. Extensions require coordinated updates.
- **Backlog status drift is acknowledged and tolerated** — project.md does not prescribe a reconciliation policy. This work introduces one.
- **Skill/hook changes are shared-infrastructure** (criticality default `high`): observability surfaces consumed by every Claude Code session start.

### From `bin/.events-registry.md`

Existing events this work consumes (no new ones produced):

- `phase_transition` — emitted at phase boundaries (research→specify→plan→implement→review→complete).
- `feature_complete` — terminal; schema `merge_anchor: "review" | "merge"`.
- `feature_wontfix` — terminal operator-decided halt (per `wontfix.md`).
- `feature_paused` — overnight runner non-terminal interruption.
- `lifecycle_start`, `spec_approved`, `plan_approved`, `complexity_override`, `criticality_override` — approval and override sentinels.

### Hook constraints

- **Fail-open**: SessionStart hooks must exit 0 even on errors (per scan_lifecycle.py defensive pattern at lines 533-539, 663-664, 721-726, 754-771).
- **Sandbox**: runs under the standard hook sandbox; no network; reads under `cortex/`.

## Tradeoffs & Alternatives

- **A. Call the canonical detector + append mismatch annotation in the SessionStart generator.** Keep `detect_lifecycle_phase` as the events-log-derived phase; layer a backlog `status:` read in `scan_lifecycle.py`; emit a mismatch annotation when they disagree. ~30-50 LOC if naive. **Pros**: zero detector duplication, additive change, preserves canonical-detector reuse. **Cons**: leaves `detect_lifecycle_phase` gaps (no `feature_paused` rung — false positives for legitimately paused features whose backlog correctly says `in_progress`); doesn't address slug-resolver duplication.

- **B. Inline a parallel reader.** Bypass `detect_lifecycle_phase`; inline a small events.log scan in scan_lifecycle.py. **Pros**: avoids one function-call frame. **Cons**: creates a third phase-detection implementation; violates the structural-exception comment in `statusline.sh:382-394`; zero performance gain. Rejected.

- **C. Source-only display, no phase derivation.** Drop the `(Phase)` label; let `/cortex-core:lifecycle resume` show state. **Pros**: simplest patch. **Cons**: loses the operator signal that drives "resume the one in Review"; sidesteps the ticket's stated goal. Rejected.

- **D. Both-source display always.** Render `{slug} (events:phase / backlog:status)` for every entry, mismatch suffix only on disagreement. **Pros**: maximum transparency. **Cons**: verbosity tax on the 95%+ no-mismatch case; doubles entry length; conflates execution phase with durable backlog status at the rendering layer. Rejected.

- **E. Fix the upstream invariant.** Patch `complete.md`, `wontfix.md`, review-verdict handlers, and `cortex-update-item` to keep backlog `status:` reliably in sync with events. **Pros**: durable root-cause fix. **Cons**: doesn't help the existing historical lifecycles whose state already diverged; bundles invariant audit with a UI patch. Best filed as a sibling backlog ticket.

- **F. Extend `detect_lifecycle_phase` to recognize `feature_paused` (and possibly `feature_wontfix` redundantly).** ~15 LOC in `_detect_lifecycle_phase_inner`. **Pros**: eliminates the #209 misclassification at source; benefits all 5+ peer consumers; reduces false-positive mismatches. **Cons**: changes the contract of a widely-consumed canonical helper — needs the parity test at `tests/test_lifecycle_phase_parity.py` to be updated; the behavior change ripples into statusline, dashboard, overnight status. Strong candidate for sequencing **before** A.

**Recommended approach**: F + A together, with E filed as a sibling follow-up. F fixes the canonical detector's known gap so the reconciliation in A has fewer false positives to suppress; A is the minimum operator-visible change that satisfies the ticket's stated goal; E is durable but independently scoped.

## Adversarial Review

The adversarial agent surfaced several findings the synthesis above should not gloss over. Summarized:

1. **The "prefer events-log truth" rule has hidden ambiguity**. The ticket's example `(Review/lifecycle, in_progress/backlog, mismatch)` shows both values; Agent 4's recommended format `[backlog: complete — mismatch]` shows only one side. Neither composes cleanly with compound `_phase_label` outputs like `Implement (3/5 tasks done)` or `Complete (awaiting merge)`. The spec must pick ONE display contract and validate it against all 9 phase-label shapes.

2. **`detect_lifecycle_phase` is mostly artifact-presence, not events-log truth**. Only rung 1 (`feature_complete`) reads events.log; rungs 2-6 are file-presence checks on review.md / plan.md / spec.md / research.md. The motivating #075 case ("stale planning artifacts only" + backlog says `complete`) needed rung 1 to fire — but if events.log was missing the detector silently fell through to rung 4 (`implement` from plan.md tally). The bug at #075's root may be "events.log absent → silent fall-through", not "reconciliation against backlog needed".

3. **The 10K cap is realistic, not theoretical**. ~90 non-archive lifecycle dirs in this repo; even after 30-day staleness filter, ~40 entries × ~100 chars/line with mismatch annotation = ~4K + pipeline-context prepend (1-2K) + active-feature header + metrics line. One bad week blows the cap. Need: prioritize mismatch-bearing rows first; truncate non-mismatches with `… +N more`; emit a `mismatches: N` count header line that survives truncation.

4. **Backlog slug resolution is already a 3-way drift problem**. Adding a 4th resolver in `scan_lifecycle.py` worsens #254's surface. Concrete failure: ticket #209's `lifecycle_slug` was historically unset; naive title-slugify resolution returned no match for the very feature that motivates the ticket. Either block on #254 (resolver unification) OR use the existing `cortex/backlog/index.json` which already keys backlog items by `lifecycle_slug`.

5. **The active-feature header also needs the annotation** — if the active feature is the mismatched one, the operator must see it in BOTH places. `_interrupted_hint()` is phase-specific; its text must be regenerated consistently with whichever side won. This is not "additive ~30-50 LOC" — it's more like 100-150 LOC plus the phase↔status matrix tests.

6. **`feature_paused → in_progress` is a steady-state legitimate mapping, not drift**. `outcome_router.py:_OVERNIGHT_TO_BACKLOG` maps `paused → in_progress` deliberately — a paused feature IS in progress from the backlog's perspective. A naive mismatch detector flags this as drift. The reconciler needs a `feature_paused`-aware ladder (which depends on Alternative F) OR an explicit "expected-divergence" allowlist that suppresses the mismatch when the divergence is the documented mapping.

7. **Status vocabulary is many-to-many with phase**. In-the-wild values include `backlog, ready, refined, in_progress, implementing, complete, done, resolved, abandoned, blocked, closed, deferred, proposed, superseded, wontfix`. Many phase↔status cells are many-to-many (`refined` is compatible with specify/plan/implement; `in_progress` is compatible with most non-terminal phases). The spec needs a `is_status_compatible(phase, status) -> bool` truth table (frozenset-valued dict in common.py), tested against all known phase↔status combinations.

8. **Pipeline-state prepend competes for the 10K budget**. scan_lifecycle.py:441-447 prepends `pipeline_state.context_string`. Cap-budget needs both. No prioritization rule proposed.

9. **#075 evidence may indicate the stale-filter is broken**. Feature shipped 2026-04-14; surfaced in SessionStart on 2026-05-20 (~36 days). Filter cutoff is 30 days — should have fired. Either (a) lifecycle dir had a phantom recent event from a cleanup attempt that touched events.log, (b) filter uses mtime not last-event-content, or (c) filter wasn't enabled at the time. None of the research agents read #075's actual events.log to confirm. Possibly a separate bug worth a sibling ticket.

10. **Sequence Alternative F first**: extending `detect_lifecycle_phase` with `feature_paused` (and explicit-fallthrough handling for empty events.log) reduces the false-positive surface before the reconciler reads it. The adversarial agent's mitigation #1 explicitly recommends this sequencing.

## Open Questions

- **Display format contract**: which format does the spec pick, given that the ticket's example `(events_phase/lifecycle, backlog_status/backlog, mismatch)` does not compose with compound `_phase_label` outputs (`Implement (3/5 tasks done)`, `Complete (awaiting merge)`)? Three candidates: (i) ticket's inline format with the phase label escaped or simplified; (ii) Agent 4's `[backlog: status — mismatch]` annotation suffix; (iii) adversarial's structurally-distinct annotation line `  - {slug} ({phase_label}) [mismatch: backlog={status}]`. Resolved in Spec by user choice.

- **Sequencing**: should this ticket land Alternative F (extend `detect_lifecycle_phase` with `feature_paused` rung) BEFORE or AS PART OF Alternative A (layer backlog reconciliation in scan_lifecycle.py)? If F is split into a sibling ticket, A is exposed to false positives on every paused feature. If F is bundled, scope grows and the parity test at `tests/test_lifecycle_phase_parity.py` must be updated. Resolved in Spec by user.

- **Backlog slug resolution**: this work should NOT introduce a 4th resolver. Choose: (a) block on #254 (unified resolver); (b) consume `cortex/backlog/index.json`'s `lifecycle_slug` keys directly as a read-only map; (c) other. Resolved in Spec by user.

- **Phase↔status compatibility matrix**: what is the canonical mapping? Some cells are many-to-many (`refined` ↔ {specify, plan, implement}; `in_progress` ↔ most non-terminal phases). The spec must enumerate this matrix as a `is_status_compatible(phase, status)` helper — needs user input on edge cases like `superseded`, `proposed`, `abandoned` that have no clean lifecycle-phase mirror.

- **Active-feature header annotation**: does the mismatch annotation also apply to the active-feature header (and the `_interrupted_hint()` text), or only to the "Other incomplete lifecycles" enumeration? The adversarial review says BOTH; the ticket is silent. Resolved in Spec.

- **10K cap mitigation**: priority ordering rule (mismatches first), truncation rule (`… +N more`), and a count-header line (`mismatches: N`) that survives truncation. Spec must specify the exact rule.

- **#075 root-cause**: is the staleness filter broken (separate bug worth its own ticket), or is the silent fall-through when events.log is absent the real failure? Defer to a separate diagnostic ticket if the answer is "filter is broken"; address in F if "fall-through is the issue".

- **`feature_paused` semantics**: does extending the detector with a `feature_paused` rung emit `"paused"` as a new phase value (which ripples through statusline, dashboard, overnight status display code) or `"implement-paused"` (a sub-state)? Resolved in Spec.

## Considerations Addressed

- **Locate the actual code that generates the SessionStart additionalContext lifecycle-summary block**: `cortex_command/hooks/scan_lifecycle.py:_build_additional_context()` (lines 345-457), called from `main()`. The ticket's hedge between `plugins/cortex-core/hooks/` and `cortex_command/` resolves entirely to `cortex_command/hooks/scan_lifecycle.py`.

- **Determine whether `cortex-common detect-phase` already encapsulates the rule**: it does for events.log rung 1 (`feature_complete`) and `feature_wontfix`, but the rest of the ladder is artifact-presence inference, not events-log truth. Critically, `feature_paused` is NOT in the ladder — that is the #209 root cause. Recommendation: extend the detector (Alternative F) so the SessionStart summary can reuse it without inheriting the gap.

- **Map the full set of input shapes**: 8 shapes mapped in Codebase Analysis §6 (events.log absent, only stale phase_transitions pre-dating `status:complete`, `feature_paused` as most recent event, `feature_complete` present, `review.md` verdict APPROVED/CHANGES_REQUESTED/REJECTED, plan.md all-checked, spec.md exists, both absent). The proposed precedence ladder mirrors the existing `_detect_lifecycle_phase_inner` with `feature_paused` added per Alternative F.

- **Compare peer observability surfaces**: statusline.sh, dashboard, `cortex overnight status` all call `detect_lifecycle_phase`. None currently cross-checks backlog `status:`. "Prefer events-log truth" is therefore NEW policy, not consistent precedent — but it is aligned with the canonical-detector reuse pattern these surfaces already follow.

- **Identify the precise data fields needed to render the mismatch string**: events-phase string from `_encode_phase()`, backlog-status string from `_STATUS_LINE_RE` parse, and a `is_status_compatible(phase, status)` predicate (to be defined in `common.py` per the spec). The display format itself remains an open question above.
